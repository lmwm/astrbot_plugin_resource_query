# 插件更新模块
#
# 把「插件自身更新」也做成一个标准功能模块：
#   - 配置（代理、重试次数）由 Views 管理
#   - 通过 `/query update` 触发检查与更新
#   - 启用开关由 AstrBot 原生配置管理

from __future__ import annotations

from ...core.module import ModuleBase
from .updater import check_update, do_update, get_current_version, reload_plugin
from .utils import get_config_fields as _load_config_fields
from .utils import get_default_config as _load_default_config


class UpdateModule(ModuleBase):
    # 插件更新模块

    #  元信息

    @property
    def module_name(self) -> str:
        # 模块标识
        return "update"

    @property
    def module_title(self) -> str:
        # 模块显示名
        return "插件更新"

    @property
    def module_icon(self) -> str:
        # 模块图标
        return "⇧"

    @property
    def module_desc(self) -> str:
        # 模块描述
        return "从 GitHub 检查并更新插件自身"

    #  模块配置

    def get_default_config(self) -> dict:
        # 模块默认配置（来自 config.yaml）
        return _load_default_config()

    def get_config_fields(self) -> list[dict]:
        # 模块配置字段定义（来自 config.yaml）
        return _load_config_fields()

    #  指令

    def get_commands(self) -> list[dict]:
        # 本模块指令列表
        #
        #         该模块通过 `/query update` 触发，因此指令名带 `query ` 前缀，
        #         便于帮助信息正确展示。
        return [{"name": "query update", "desc": "检查并更新插件"}]

    async def handle_command(self, command: str, args: list[str], event):
        # 处理更新指令
        if command != "update":
            return

        config = self.load_module_config()
        proxy = str(config.get("proxy") or "").strip()
        max_retries = config.get("max_retries", 3)
        try:
            max_retries = int(max_retries)
        except (TypeError, ValueError):
            max_retries = 3

        yield event.plain_result(
            f"正在检查更新（当前版本 v{get_current_version()}）..."
        )

        check = await check_update(proxy, max_retries, force=True)
        if check.get("error"):
            yield event.plain_result(f"× 检查更新失败: {check['error']}")
            return

        yield event.plain_result(f"远端版本 v{check['latest']}，正在重新安装...")

        result = await do_update(proxy, max_retries)
        if "√" not in result:
            yield event.plain_result(result)
            return

        yield event.plain_result(f"{result}\n{await reload_plugin(self._context)}")

    #  Views 接口

    def config_payload(self, config: dict) -> dict:
        # 额外返回当前版本号，供 Views 展示
        config["current_version"] = get_current_version()
        return config

    def accept_config_payload(self, payload: dict, config: dict) -> dict:
        # 只接受 config.yaml 声明的键，避免把 current_version 等只读字段写回
        known = _load_default_config()
        return {k: v for k, v in payload.items() if k in known}
