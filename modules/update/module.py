# 插件更新模块
#
# 两种触发共用同一执行体：
#   - 聊天：`/query update`，总是重装同步，结果回消息
#   - 定时：AstrBot cron 回调，只有远端版本不同才更新，只写日志
#
# 日志目录：plugin_data/<插件>/logs/update/，只保留最近 10 个文件。

from __future__ import annotations

import asyncio
import logging

from ...core.module import ModuleBase
from .journal import UpdateJournal
from .schedule import UpdateSchedule
from .updater import check_update, do_update, get_current_version, reload_plugin
from .utils import get_config_fields as _load_config_fields
from .utils import get_default_config as _load_default_config

logger = logging.getLogger(__name__)


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

    #  指令

    def get_commands(self) -> list[dict]:
        return [{"name": "query update", "desc": "检查并更新插件"}]

    async def handle_command(self, command: str, args: list[str], event):
        # 聊天触发：进度与结果都发回会话
        if command != "update":
            return

        async def notify(text: str) -> None:
            await event.send(event.message_result().message(text))

        outcome = await self._execute("chat", force=True, notify=notify)
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
            config = self.load_module_config()
            proxy = str(config.get("proxy") or "").strip()
            retries = self._to_int(config.get("max_retries"), 3)
            current = get_current_version()

            journal = UpdateJournal(self.get_data_path())
            journal.start(trigger, current)

            try:
                if notify:
                    await notify(f"正在检查更新（当前版本 v{current}）...")

                check = await check_update(proxy, retries, force=force)
                if check.get("error"):
                    journal.append(f"result=error error={check['error']}")
                    journal.prune()
                    return {
                        "ok": False,
                        "message": f"× 检查更新失败: {check['error']}",
                    }

                latest = str(check.get("latest") or "")
                has_update = bool(check.get("has_update"))
                journal.append(f"remote={latest} has_update={has_update}")

                if not force and not has_update:
                    journal.append("result=skip（已是最新）")
                    journal.prune()
                    return {"ok": True, "message": f"已是最新版本 v{current}"}

                if notify:
                    await notify(f"远端版本 v{latest}，正在重新安装...")

                result = await do_update(proxy, retries)
                journal.append(f"update={result}")
                if "√" not in result:
                    journal.prune()
                    return {"ok": False, "message": result}

                # 重载会卸载当前插件，先把更新结果落盘
                journal.append("reload=发起中")
                journal.prune()

                reload_text = await reload_plugin(self._context)
                journal.append(f"reload={reload_text}")
                journal.prune()
                return {"ok": True, "message": f"{result}\n{reload_text}"}
            except Exception as e:  # noqa: BLE001
                journal.append(f"result=exception {type(e).__name__}: {e}")
                journal.prune()
                logger.error(f"[update] 更新异常: {type(e).__name__}: {e}")
                return {"ok": False, "message": f"× 更新异常: {e}"}

    @staticmethod
    def _to_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

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
