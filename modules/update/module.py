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
        return _load_config_fields()

    def get_config_groups(self) -> list[dict]:
        # 消息模板单独一页；网络/自动更新等其余配置留在「模块设置」
        return [
            {
                "key": "messages",
                "label": "消息模板",
                "hint": (
                    "可用变量：{current} 当前版本；{latest} 远端版本；"
                    "{sha}/{sha7} 完整/短提交号；{elapsed} 耗时（秒）；"
                    "{error} 错误信息"
                ),
            }
        ]

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

            journal = UpdateJournal(self.get_data_path())
            journal.start(trigger, current)

            async def say(key: str, variables: dict) -> None:
                # 过程提示：聊天触发时直接发送；定时触发不通知
                if notify is None:
                    return
                text = self._render(config.get(key, ""), variables)
                if text:
                    await notify(text)

            try:
                await say("message_checking", {"current": current})

                check = await check_update(
                    proxy, retries, force=force, current_commit=current_commit
                )
                if check.get("error"):
                    error = str(check["error"])
                    journal.append(f"result=error error={error}")
                    journal.prune()
                    return {
                        "ok": False,
                        "message": self._render(
                            config.get("message_error", ""),
                            {"error": error, "current": current},
                        ),
                    }

                latest = str(check.get("latest") or "")
                remote_commit = str(check.get("remote_commit") or "")
                has_update = bool(check.get("has_update"))
                journal.append(
                    f"remote={latest} remote_commit={remote_commit} "
                    f"has_update={has_update}"
                )

                if not force and not has_update:
                    journal.append("result=skip（已是最新）")
                    journal.prune()
                    return {
                        "ok": True,
                        "message": self._render(
                            config.get("message_skip", ""),
                            {"current": current, "latest": latest},
                        ),
                    }

                await say("message_found", {"current": current, "latest": latest})

                result = await do_update(proxy, retries, sha=remote_commit)
                sha = str(result.get("sha") or "")
                journal.append(f"update ok={bool(result.get('ok'))} sha={sha}")

                if not result.get("ok"):
                    message = str(result.get("message") or "更新失败")
                    journal.append(f"result=error message={message}")
                    journal.prune()
                    return {
                        "ok": False,
                        "message": self._render(
                            config.get("message_error", ""),
                            {"error": message, "current": current},
                        ),
                    }

                # 记录本次更新到的提交，供下次自动更新比较
                self._save_state(sha, latest)

                # 重载会卸载当前插件，先把更新结果落盘
                journal.append("reload=发起中")
                journal.prune()

                reload_text = await reload_plugin(self._context)
                elapsed = f"{time.monotonic() - started:.1f}"
                journal.append(f"reload={reload_text}")
                journal.append(f"elapsed={elapsed}s")
                journal.prune()

                return {
                    "ok": True,
                    "message": self._render(
                        config.get("message_done", ""),
                        {
                            "current": current,
                            "latest": latest,
                            "sha": sha,
                            "sha7": sha[:7],
                            "elapsed": elapsed,
                        },
                    ),
                }
            except Exception as e:  # noqa: BLE001
                journal.append(f"result=exception {type(e).__name__}: {e}")
                journal.prune()
                logger.error(f"[update] 更新异常: {type(e).__name__}: {e}")
                return {"ok": False, "message": f"× 更新异常: {e}"}

    @staticmethod
    def _render(template, variables: dict) -> str:
        # 模板变量缺失时保留原文，不让渲染失败影响更新流程
        text = str(template or "")
        try:
            return text.format(**variables)
        except (KeyError, IndexError, ValueError):
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
