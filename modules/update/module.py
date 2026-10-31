# 插件更新模块
#
# 两种触发共用同一执行体：
#   - 聊天：`/query update`，按 force_update 配置决定是否强制重装
#   - 自动：AstrBot cron 回调，版本号不同或提交号不同才更新，只写日志
#
# 日志目录：plugin_data/<插件>/logs/update/，只保留最近 10 个文件。

from __future__ import annotations

import asyncio
import logging
import time

from astrbot.api.event import MessageChain

from ...common.yaml_utils import parse_yaml, save_yaml_file
from ...core.module import ModuleBase
from .journal import UpdateJournal
from .schedule import UpdateSchedule
from .updater import check_update, do_update, get_current_version, reload_plugin
from .utils import get_config_fields as _load_config_fields
from .utils import get_default_config as _load_default_config

logger = logging.getLogger(__name__)

# 本地更新状态文件名（记录已更新到的提交）
STATE_FILE = "update_state.yaml"

# 每条消息可用的模板变量（前端变量标签据此过滤）
_MESSAGE_VARIABLES = {
    "message_checking": [
        "current",
        "latest",
        "current_sha",
        "current_sha7",
        "sha",
        "sha7",
    ],
    "message_found": [
        "current",
        "latest",
        "current_sha",
        "current_sha7",
        "sha",
        "sha7",
    ],
    "message_done": [
        "current",
        "latest",
        "current_sha",
        "current_sha7",
        "sha",
        "sha7",
        "elapsed",
    ],
    "message_skip": [
        "current",
        "latest",
        "current_sha",
        "current_sha7",
        "sha",
        "sha7",
    ],
    "message_error": ["current", "error"],
}


class UpdateModule(ModuleBase):
    # 插件更新模块

    def __init__(self, plugin_dir, plugin_name: str) -> None:
        super().__init__(plugin_dir, plugin_name)
        self._lock = asyncio.Lock()
        self._schedule: UpdateSchedule | None = None

    #  元信息

    @property
    def module_name(self) -> str:
        return "update"

    @property
    def module_title(self) -> str:
        return "插件更新"

    @property
    def module_icon(self) -> str:
        return "⇧"

    @property
    def module_desc(self) -> str:
        return "从 GitHub 检查并更新插件自身"

    #  生命周期

    async def on_load(self) -> None:
        # 插件加载完成后注册定时更新
        await super().on_load()
        self._schedule = UpdateSchedule(
            self._context, self._plugin_name, self._run_scheduled
        )
        await self._sync_schedule()

    async def on_unload(self) -> None:
        if self._schedule is not None:
            await self._schedule.clear()

    async def _sync_schedule(self) -> None:
        if self._schedule is None:
            return

        config = self.load_module_config()
        await self._schedule.sync(
            enabled=bool(config.get("schedule_enabled", True)),
            cron_expression=str(config.get("schedule_cron") or "").strip(),
        )

    #  模块配置

    def get_default_config(self) -> dict:
        return _load_default_config()

    def get_config_fields(self) -> list[dict]:
        # 为每个消息模板字段标注可用变量
        fields = _load_config_fields()
        for field in fields:
            allowed = _MESSAGE_VARIABLES.get(field.get("key"))
            if allowed:
                field["variables"] = list(allowed)
        return fields

    def get_config_groups(self) -> list[dict]:
        # 消息模板单独一页；网络/自动更新等其余配置留在「模块设置」
        return [
            {
                "key": "messages",
                "label": "消息模板",
            }
        ]

    def get_var_definitions(self) -> dict[str, str]:
        # 消息模板可用变量（模板页的变量标签与预览使用）
        return {
            "current": "当前版本",
            "latest": "远端版本",
            "current_sha": "当前版本提交号",
            "current_sha7": "当前版本短提交号",
            "sha": "远端提交号",
            "sha7": "远端短提交号",
            "elapsed": "耗时（秒）",
            "error": "错误信息",
        }

    def get_var_samples(self) -> dict[str, str]:
        # 变量示例值，供预览使用
        return {
            "current": "5.9.23",
            "latest": "5.9.24",
            "current_sha": "1101942f2ee9b12772ae7e6372794b1d09d8d57",
            "current_sha7": "1101942",
            "sha": "2c54e39abcdef0123456789abcdef0123456789",
            "sha7": "2c54e39",
            "elapsed": "5.2",
            "error": "网络连接超时",
        }

    #  指令

    def get_commands(self) -> list[dict]:
        return [{"name": "query update", "desc": "检查并更新插件"}]

    async def handle_command(self, command: str, args: list[str], event):
        # 聊天触发：进度与结果都发回会话
        if command != "update":
            return

        async def notify(text: str) -> None:
            await event.send(MessageChain().message(text))

        config = self.load_module_config()
        force = bool(config.get("force_update", True))
        outcome = await self._execute("chat", force=force, notify=notify)
        yield event.plain_result(outcome["message"])

    #  执行体

    async def _run_scheduled(self) -> None:
        # 定时触发：不通知聊天，结果只写日志
        try:
            await self._execute("schedule", force=False)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[update] 定时更新异常: {type(e).__name__}: {e}")

    async def _execute(self, trigger: str, force: bool, notify=None) -> dict:
        # 同一把锁避免定时任务与手动更新并发重装
        async with self._lock:
            started = time.monotonic()
            config = self.load_module_config()
            proxy = str(config.get("proxy") or "").strip()
            retries = self._to_int(config.get("max_retries"), 3)
            current = get_current_version()
            current_commit = str(self._load_state().get("commit") or "")

            # 模板变量始终提供完整键，尚未产生值的阶段为空字符串
            variables = {
                "current": current,
                "latest": "",
                "current_sha": current_commit,
                "current_sha7": current_commit[:7],
                "sha": "",
                "sha7": "",
                "elapsed": "",
                "error": "",
            }

            journal = UpdateJournal(self.get_data_path())
            journal.start(trigger, current)

            async def say(key: str) -> None:
                # 过程提示：聊天触发时直接发送；定时触发不通知
                if notify is None:
                    return
                text = self._render(config.get(key, ""), variables)
                if text:
                    await notify(text)

            try:
                check = await check_update(
                    proxy, retries, force=force, current_commit=current_commit
                )
                if check.get("error"):
                    error = str(check["error"])
                    variables["error"] = error
                    journal.append(f"result=error error={error}")
                    journal.prune()
                    return {
                        "ok": False,
                        "message": self._render(
                            config.get("message_error", ""), variables
                        ),
                    }

                latest = str(check.get("latest") or "")
                remote_commit = str(check.get("remote_commit") or "")
                has_update = bool(check.get("has_update"))
                variables["latest"] = latest
                variables["sha"] = remote_commit
                variables["sha7"] = remote_commit[:7]
                journal.append(
                    f"remote={latest} remote_commit={remote_commit} "
                    f"has_update={has_update}"
                )

                await say("message_checking")

                if not force and not has_update:
                    journal.append("result=skip（已是最新）")
                    journal.prune()
                    return {
                        "ok": True,
                        "message": self._render(
                            config.get("message_skip", ""), variables
                        ),
                    }

                await say("message_found")

                result = await do_update(proxy, retries, sha=remote_commit)
                sha = str(result.get("sha") or "")
                variables["sha"] = sha
                variables["sha7"] = sha[:7]
                journal.append(f"update ok={bool(result.get('ok'))} sha={sha}")

                if not result.get("ok"):
                    message = str(result.get("message") or "更新失败")
                    variables["error"] = message
                    journal.append(f"result=error message={message}")
                    journal.prune()
                    return {
                        "ok": False,
                        "message": self._render(
                            config.get("message_error", ""), variables
                        ),
                    }

                # 记录本次更新到的提交，供下次自动更新比较
                self._save_state(sha, latest)

                # 重载会卸载当前插件，先把更新结果落盘
                journal.append("reload=发起中")
                journal.prune()

                reload_text = await reload_plugin(self._context)
                elapsed = f"{time.monotonic() - started:.1f}"
                variables["elapsed"] = elapsed
                journal.append(f"reload={reload_text}")
                journal.append(f"elapsed={elapsed}s")
                journal.prune()

                return {
                    "ok": True,
                    "message": self._render(config.get("message_done", ""), variables),
                }
            except Exception as e:  # noqa: BLE001
                journal.append(f"result=exception {type(e).__name__}: {e}")
                journal.prune()
                logger.error(f"[update] 更新异常: {type(e).__name__}: {e}")
                return {"ok": False, "message": f"× 更新异常: {e}"}

    @staticmethod
    def _render(template, variables: dict) -> str:
        # 缺失的变量保留 {name} 占位符，其余照常替换
        text = str(template or "")

        class _SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        try:
            return text.format_map(_SafeDict(variables))
        except (ValueError, IndexError):
            return text

    @staticmethod
    def _to_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    #  更新状态（记录本地已更新到的提交）

    def _state_path(self):
        return self.get_data_path() / STATE_FILE

    def _load_state(self) -> dict:
        path = self._state_path()
        if not path.exists():
            return {}
        try:
            data = parse_yaml(path.read_text(encoding="utf-8"))
        except OSError:
            return {}
        return data if isinstance(data, dict) else {}

    def _save_state(self, commit: str, version: str) -> None:
        save_yaml_file(self._state_path(), {"commit": commit, "version": version})

    #  Views 接口

    def config_payload(self, config: dict) -> dict:
        # 额外返回当前版本号，供 Views 展示
        config["current_version"] = get_current_version()
        return config

    def accept_config_payload(self, payload: dict, config: dict) -> dict:
        # 只接受 config.yaml 声明的键，避免把 current_version 等只读字段写回
        known = _load_default_config()
        return {k: v for k, v in payload.items() if k in known}

    async def api_save_config(self):
        # 保存后立即按新配置重排定时任务
        response = await super().api_save_config()
        await self._sync_schedule()
        return response

    async def api_reset_config(self):
        # 恢复默认后同样重排定时任务
        response = await super().api_reset_config()
        await self._sync_schedule()
        return response
