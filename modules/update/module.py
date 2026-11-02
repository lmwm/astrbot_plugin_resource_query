# 插件更新模块
#
# 两种触发方式：
#   - 聊天 `/query update`：总是强制更新（不比较版本号），先发检查中、再发检测结果与结果
#   - 自动：AstrBot cron 回调，只比较版本号，有新版本才更新，不发送消息只写日志
#
# 当前版本读插件目录的 metadata.yaml；不保存、也不读取提交号状态。
# 日志：plugin_data/<插件>/logs/update.log（追加，每行带时间戳，运行间有分割线）。

from __future__ import annotations

import asyncio

from astrbot.api.event import MessageChain

from ...common.module_log import log_separator, module_logger
from ...core.module import ModuleBase
from .config import CONFIG_FIELDS, CONFIG_GROUPS, VAR_SAMPLES, VARIABLES
from .schedule import UpdateSchedule
from .updater import check_update, do_update, get_current_version, reload_plugin

logger = module_logger("update")


class UpdateModule(ModuleBase):
    # 插件更新模块

    #  默认配置（来自 config.py）

    config_fields = CONFIG_FIELDS
    config_groups = CONFIG_GROUPS
    variable_defaults = VARIABLES
    var_samples = VAR_SAMPLES

    def __init__(self, plugin_dir, plugin_name: str) -> None:
        super().__init__(plugin_dir, plugin_name)
        self._lock = asyncio.Lock()
        self._schedule: UpdateSchedule | None = None
        # 最近一次 /query update 的会话，供定时更新成功后发送消息
        self._last_session = ""

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
            enabled=bool(config.get("schedule_enabled")),
            cron_expression=str(config.get("schedule_cron") or "").strip(),
        )

    #  指令

    def get_commands(self) -> list[dict]:
        return [{"name": "query update", "desc": "检查并更新插件（总是重装）"}]

    async def handle_command(self, command: str, args: list[str], event):
        # 聊天触发：总是强制更新，不比较版本号
        if command != "update":
            return

        self._last_session = str(event.unified_msg_origin or "")

        async def notify(text: str) -> None:
            await event.send(MessageChain().message(text))

        outcome = await self._execute("chat", force=True, notify=notify)
        if outcome["message"]:
            yield event.plain_result(outcome["message"])

    #  执行体

    async def _run_scheduled(self) -> None:
        # 定时触发：只按版本号判断，不通知聊天，结果只写日志
        try:
            await self._execute("schedule", force=False)
        except Exception as e:  # noqa: BLE001
            logger.error(f"定时更新任务异常：{type(e).__name__}: {e}")

    async def _execute(self, trigger: str, force: bool, notify=None) -> dict:
        # 同一把锁避免定时任务与手动更新并发重装
        async with self._lock:
            config = self.load_module_config()
            proxy = str(config.get("proxy") or "").strip()
            retries = self._to_int(
                config.get("max_retries"),
                int(self._config_store.default_values().get("max_retries") or 0),
            )
            current = get_current_version()

            # 模板变量按阶段赋值；未赋值的占位符在渲染时原样保留
            variables = {"current": current}

            trigger_name = "聊天指令" if trigger == "chat" else "定时任务"
            result_names = {
                "ok": "成功",
                "skip": "跳过（版本未变化）",
                "error": "失败",
                "reload_failed": "失败（重载失败）",
                "exception": "失败（异常）",
            }

            def end(result: str, error: str = "") -> None:
                # 本次运行的结束分割线
                detail = f"{trigger_name}结束：{result_names.get(result, result)}"
                if error:
                    detail += f"，原因：{error}"
                log_separator(logger, detail)

            log_separator(logger, f"{trigger_name}开始：当前版本 v{current}")

            async def say(key: str) -> None:
                # 过程提示：聊天触发时直接发送；定时触发不通知
                if notify is None:
                    return
                text = self._render(config.get(key), variables)
                if text:
                    await notify(text)

            def result_message(key: str) -> str:
                # 结果消息只在聊天触发时生成；定时触发不发送
                if notify is None:
                    return ""
                return self._render(config.get(key), variables)

            try:
                # 先回应指令，再开始联网检查
                await say("message_checking")

                check = await check_update(proxy, retries, force=force)
                if check.get("error"):
                    error = str(check["error"])
                    variables["error"] = error
                    logger.error(f"检查更新失败：{error}")
                    end("error", error)
                    return {
                        "ok": False,
                        "message": result_message("message_error"),
                    }

                latest = str(check.get("latest") or "")
                remote_commit = str(check.get("remote_commit") or "")
                has_update = bool(check.get("has_update"))
                variables["latest"] = latest
                variables["sha"] = remote_commit
                variables["sha7"] = remote_commit[:7]
                logger.info(
                    f"检查完成：本地 v{current} → 远端 v{latest or '未知'}，"
                    f"远端提交 {remote_commit[:7] or '未知'}，"
                    f"需要更新：{'是' if has_update else '否'}"
                )

                # 检测结果：当前版本与远端版本对比
                await say("message_found")

                if not force and not has_update:
                    logger.info("版本号未变化，跳过更新")
                    end("skip")
                    return {"ok": True, "message": ""}

                result = await do_update(proxy, retries, sha=remote_commit)
                sha = str(result.get("sha") or "")
                variables["sha"] = sha
                variables["sha7"] = sha[:7]
                logger.info(
                    f"源码归档已替换：提交 {sha[:7] or '未知'}，结果 {'成功' if result.get('ok') else '失败'}"
                )

                if not result.get("ok"):
                    error = str(result.get("error") or "")
                    variables["error"] = error
                    logger.error(f"更新插件文件失败：{error}")
                    end("error", error)
                    return {
                        "ok": False,
                        "message": result_message("message_error"),
                    }

                # 文件已替换：重读插件目录版本，{current} 表示本地更新后的版本
                current = get_current_version()
                variables["current"] = current
                logger.info(f"本地版本已更新为 v{current}")

                # 重载会卸载当前插件，先记录再发起
                logger.info("开始重载插件")

                reload = await reload_plugin(self._context)
                if not reload.get("ok"):
                    error = str(reload.get("error") or "")
                    variables["error"] = error
                    logger.error(f"插件重载失败：{error}")
                    end("reload_failed", error)
                    return {
                        "ok": False,
                        "message": result_message("message_error"),
                    }

                logger.info("插件重载成功")
                end("ok")

                done_text = self._render(config.get("message_done"), variables)
                if trigger == "schedule":
                    await self._send_scheduled_message(config, done_text)
                return {
                    "ok": True,
                    "message": done_text if notify is not None else "",
                }
            except Exception as e:  # noqa: BLE001
                variables["error"] = f"{type(e).__name__}: {e}"
                logger.error(f"更新过程出现异常：{variables['error']}")
                end("exception", variables["error"])
                return {
                    "ok": False,
                    "message": result_message("message_error"),
                }

    async def _send_scheduled_message(self, config: dict, text: str) -> None:
        # 定时更新成功后，把完成消息发送到配置或最近一次指令的会话
        target = str(config.get("notify_session") or "").strip() or self._last_session
        if not target:
            logger.warning(
                "定时更新成功，但没有通知会话（未配置且本次启动后没有 /query update）"
            )
            return
        if self._context is None:
            logger.warning("定时更新成功，但上下文不可用，无法发送消息")
            return

        try:
            await self._context.send_message(target, MessageChain().message(text))
            logger.info(f"定时更新成功，已发送完成消息到会话：{target}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"定时更新成功，但发送完成消息失败：{type(e).__name__}: {e}")

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

    #  Views 接口

    def config_payload(self, config: dict) -> dict:
        # 额外返回当前版本号，供 Views 展示
        config["current_version"] = get_current_version()
        return config

    def accept_config_payload(self, payload: dict, config: dict) -> dict:
        # 只接受用户配置中存在的键，避免把 current_version 等只读字段写回
        known = {field["key"] for field in self.get_config_fields()}
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
