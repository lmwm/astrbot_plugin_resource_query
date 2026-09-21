"""插件更新模块

把「插件自身更新」也做成一个标准功能模块：
  - 配置（代理、重试次数）由 Pages 管理
  - 通过 `/query update` 触发检查与更新
  - 启用开关由 AstrBot 原生配置管理
"""

from __future__ import annotations

from ...core.module import ModuleBase
from .updater import check_update, do_update, get_current_version, reload_plugin

# 模块配置字段
_CONFIG_FIELDS = [
    {
        "key": "proxy",
        "label": "GitHub 代理",
        "type": "text",
        "hint": "如 https://gh-proxy.cn/，留空不使用代理",
    },
    {
        "key": "max_retries",
        "label": "请求重试次数",
        "type": "int",
        "hint": "网络请求失败时的重试次数",
    },
]

# 默认配置
_DEFAULT_CONFIG = {
    "proxy": "https://gh-proxy.cn/",
    "max_retries": 3,
}


class UpdateModule(ModuleBase):
    """插件更新模块"""

    # ══════════════════════════════════════════
    #  元信息
    # ══════════════════════════════════════════

    @property
    def module_name(self) -> str:
        """模块标识"""
        return "update"

    @property
    def module_title(self) -> str:
        """模块显示名"""
        return "插件更新"

    @property
    def module_icon(self) -> str:
        """模块图标"""
        return "⬆️"

    @property
    def module_desc(self) -> str:
        """模块描述"""
        return "从 GitHub 检查并更新插件自身"

    # ══════════════════════════════════════════
    #  模块配置
    # ══════════════════════════════════════════

    def get_default_config(self) -> dict:
        """模块默认配置

        Returns:
            代理与重试次数默认值。
        """
        return dict(_DEFAULT_CONFIG)

    def get_config_fields(self) -> list[dict]:
        """模块配置字段定义

        Returns:
            字段列表。
        """
        return _CONFIG_FIELDS

    # ══════════════════════════════════════════
    #  指令
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        """本模块指令列表

        该模块通过 `/query update` 触发，因此指令名带 `query ` 前缀，
        便于帮助信息正确展示。

        Returns:
            指令定义列表。
        """
        return [{"name": "query update", "desc": "检查并更新插件"}]

    async def handle_command(self, command: str, args: list[str], event):
        """处理更新指令

        Args:
            command: 指令名称（固定为 "update"）。
            args: 指令参数（未使用）。
            event: 消息事件。

        Yields:
            消息结果。
        """
        if command != "update":
            return

        config = self.load_module_config()
        proxy = str(config.get("proxy") or "").strip()
        try:
            max_retries = int(config.get("max_retries") or 3)
        except (TypeError, ValueError):
            max_retries = 3

        yield event.plain_result(f"正在检查更新（当前版本 v{get_current_version()}）...")

        check = await check_update(proxy, max_retries, force=True)
        if check.get("error"):
            yield event.plain_result(f"❌ 检查更新失败: {check['error']}")
            return

        yield event.plain_result(f"远端版本 v{check['latest']}，正在重新安装...")

        result = await do_update(proxy, max_retries)
        if "✅" not in result:
            yield event.plain_result(result)
            return

        yield event.plain_result(f"{result}\n{await reload_plugin(self._context)}")

    # ══════════════════════════════════════════
    #  Pages 接口
    # ══════════════════════════════════════════

    def get_web_apis(self) -> list[dict]:
        """本模块的 Pages 接口

        Returns:
            接口定义列表。
        """
        return [
            {"path": "config", "handler": self._api_get_config, "methods": ["GET"], "desc": "获取更新配置"},
            {"path": "config", "handler": self._api_save_config, "methods": ["POST"], "desc": "保存更新配置"},
        ]

    async def _api_get_config(self):
        """获取更新配置"""
        from astrbot.api.web import json_response

        config = self.load_module_config()
        config["current_version"] = get_current_version()
        return json_response(config)

    async def _api_save_config(self):
        """保存更新配置"""
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        if not isinstance(payload, dict) or not payload:
            return error_response("缺少配置数据")

        config = self.load_module_config()
        config.update({k: v for k, v in payload.items() if k in _DEFAULT_CONFIG})

        if not self.save_module_config(config):
            return error_response("保存失败")

        return json_response({"status": "ok"})
