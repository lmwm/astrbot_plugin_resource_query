"""资源查询插件入口

职责保持极薄：
  1. 按 AstrBot 原生配置决定启用哪些功能模块并注册；
  2. 注册全局与各模块的 Pages 接口；
  3. 把指令分发到对应模块。

四个功能模块（均继承 `core.module.ModuleBase`）：
  - mimo   ：小米 MiMo 用量查询
  - wasu   ：华数广电流量 / 话费查询
  - jm     ：JMComic 漫画下载
  - update ：插件自身更新

新增功能模块只需两步：
  1. 在 `modules/` 下新建包并实现 `XxxModule(ModuleBase)`；
  2. 在下方 `_MODULE_CLASSES` 中登记一行。
  Pages 前端会依据模块声明的 schema 自动渲染配置页。
"""

from __future__ import annotations

from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .common.utils import load_json_file, save_json_file
from .core.manager import PluginManager
from .modules import JMModule, MimoModule, UpdateModule, WasuModule
from .modules.update.updater import get_current_version

# 插件唯一标识
PLUGIN_NAME = "astrbot_plugin_resource_query"

# 功能模块清单：模块名 → 模块类
# 新增功能时在此登记即可，无需改动其他逻辑
_MODULE_CLASSES: dict[str, type] = {
    "mimo": MimoModule,
    "wasu": WasuModule,
    "jm": JMModule,
    "update": UpdateModule,
}

# 模板变量配置文件
_VAR_CONFIG_FILE = "var_config.json"


class ResourceQueryPlugin(Star):
    """资源查询插件

    只做「注册 + 分发」，具体功能全部由各模块自治实现。
    """

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        """初始化插件

        Args:
            context: AstrBot 上下文。
            config: AstrBot 原生配置（模块启用开关）。
        """
        super().__init__(context)
        self.config = config or {}
        self._plugin_dir = Path(__file__).parent

        self._manager = PluginManager(PLUGIN_NAME, self._plugin_dir)
        self._register_modules(context)
        self._register_web_apis(context)

    # ══════════════════════════════════════════
    #  模块注册
    # ══════════════════════════════════════════

    def _register_modules(self, context: Context) -> None:
        """按 AstrBot 原生配置注册已启用的模块

        Args:
            context: AstrBot 上下文，会注入到每个模块。
        """
        enabled = self.config.get("modules") or {}

        for name, module_cls in _MODULE_CLASSES.items():
            # 未显式配置时默认启用
            if not enabled.get(f"{name}_enabled", True):
                logger.info(f"[{PLUGIN_NAME}] 模块 {name} 已在配置中禁用，跳过加载")
                continue

            module = module_cls(self._plugin_dir, PLUGIN_NAME)
            module.set_context(context)

            if not self._manager.register_module(module):
                logger.warning(f"[{PLUGIN_NAME}] 模块 {name} 注册失败（名称重复）")

    # ══════════════════════════════════════════
    #  Pages 接口
    # ══════════════════════════════════════════

    def _register_web_apis(self, context: Context) -> None:
        """注册全局接口与各模块自有接口

        Args:
            context: AstrBot 上下文。
        """
        for path, handler, methods, desc in (
            ("modules", self.get_modules, ["GET"], "获取已启用模块及其页面描述"),
            ("accounts", self.get_accounts, ["GET"], "获取所有模块的账号"),
            ("accounts", self.save_accounts, ["POST"], "保存指定模块的账号"),
            ("accounts/delete", self.delete_account, ["POST"], "删除指定账号"),
            ("template-vars", self.get_template_vars, ["GET"], "获取模板变量定义"),
            ("template-vars", self.save_template_vars, ["POST"], "保存模板变量定义"),
        ):
            context.register_web_api(f"/{PLUGIN_NAME}/{path}", handler, methods, desc)

        # 模块自有接口（路径含模块名前缀）
        for module in self._manager.get_all_modules():
            for api in module.get_web_apis():
                context.register_web_api(
                    f"/{PLUGIN_NAME}/{module.module_name}/{api['path']}",
                    api["handler"],
                    api.get("methods", ["GET"]),
                    api.get("desc", ""),
                )

    async def get_modules(self):
        """获取已启用模块的页面描述

        未启用的模块不会被注册，因此不会出现在返回结果中，
        Pages 也就不会渲染它们的配置页。

        Returns:
            JSON 响应，包含模块 schema 列表与插件版本号。
        """
        from astrbot.api.web import json_response

        return json_response({
            "version": get_current_version(),
            "modules": self._manager.get_page_schemas(),
        })

    async def get_accounts(self):
        """获取所有已启用模块的账号

        Returns:
            JSON 响应，账号列表（每项带 platform 字段）。
        """
        from astrbot.api.web import json_response

        return json_response({"accounts": self._manager.get_all_accounts()})

    async def save_accounts(self):
        """保存指定模块的账号列表

        Returns:
            JSON 响应。
        """
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        platform = str(payload.get("platform") or "").strip()
        accounts = payload.get("accounts")

        module = self._manager.get_module(platform)
        if not module:
            return error_response(f"模块 {platform or '(空)'} 未启用")

        if not isinstance(accounts, list):
            return error_response("accounts 必须是数组")

        if not module.save_accounts(accounts):
            return error_response("保存失败")

        return json_response({"status": "ok"})

    async def delete_account(self):
        """删除指定账号

        Returns:
            JSON 响应。
        """
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        platform = str(payload.get("platform") or "").strip()
        filename = str(payload.get("filename") or "").strip()

        if not platform or not filename:
            return error_response("缺少 platform 或 filename 参数")

        deleted = self._manager.delete_account(platform, filename)
        if deleted is None:
            return error_response("账号不存在或删除失败")

        name = (
            deleted.get("name")
            or deleted.get("account")
            or deleted.get("phone")
            or filename
        )
        return json_response({"status": "ok", "deleted": name})

    async def get_template_vars(self):
        """获取各模块的模板变量定义

        变量来源 = 模块声明的变量 + 用户在 Pages 中的自定义配置，
        因此在 Pages 中新增的变量刷新后不会丢失。

        Returns:
            JSON 响应，按模块名分组的变量列表。
        """
        from astrbot.api.web import json_response

        result: dict[str, dict] = {}

        for module in self._manager.get_all_modules():
            declared = module.get_var_definitions()
            if not declared:
                continue

            saved = load_json_file(module.get_config_path() / _VAR_CONFIG_FILE) or {}
            saved_map = {
                item["name"]: item
                for item in (saved.get("variables") or [])
                if isinstance(item, dict) and item.get("name")
            }

            variables = [
                {
                    "name": name,
                    "desc": saved_map.get(name, {}).get("desc") or desc,
                    "default": saved_map.get(name, {}).get("default", ""),
                    "show": saved_map.get(name, {}).get("show", True),
                }
                for name, desc in declared.items()
            ]

            # 用户在 Pages 中额外添加的变量也一并保留
            variables.extend(
                item for name, item in saved_map.items() if name not in declared
            )

            result[module.module_name] = {"variables": variables}

        return json_response(result)

    async def save_template_vars(self):
        """保存指定模块的模板变量配置

        Returns:
            JSON 响应。
        """
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        platform = str(payload.get("platform") or "").strip()
        variables = payload.get("variables")

        module = self._manager.get_module(platform)
        if not module:
            return error_response(f"模块 {platform or '(空)'} 未启用")

        if not isinstance(variables, list):
            return error_response("variables 必须是数组")

        path = module.get_config_path() / _VAR_CONFIG_FILE
        if not save_json_file(path, {"variables": variables}):
            return error_response("保存失败")

        return json_response({"status": "ok"})

    # ══════════════════════════════════════════
    #  指令
    # ══════════════════════════════════════════

    @filter.command("query")
    async def query_cmd(self, event: AstrMessageEvent):
        """/query — 显示帮助，或分发 /query <模块名>

        Args:
            event: 消息事件。

        Yields:
            消息结果。
        """
        args = self._parse_args(event, "query")

        if not args:
            yield event.plain_result(self._help_text())
            return

        name = args[0].lower()
        module = self._manager.get_module(name)

        if not module:
            enabled = "、".join(self._manager.get_module_names()) or "（无）"
            yield event.plain_result(f"× 未知功能: {name}\n已启用: {enabled}")
            return

        async for result in module.handle_command(name, args[1:], event):
            yield result

    @filter.command("mimo")
    async def mimo_cmd(self, event: AstrMessageEvent):
        """/mimo — MiMo 查询指令"""
        async for result in self._dispatch("mimo", event):
            yield result

    @filter.command("wasu")
    async def wasu_cmd(self, event: AstrMessageEvent):
        """/wasu — 华数广电查询指令"""
        async for result in self._dispatch("wasu", event):
            yield result

    @filter.command("jm", alias={"JM", "Jm", "jM"})
    async def jm_cmd(self, event: AstrMessageEvent):
        """/jm — JMComic 漫画下载指令"""
        async for result in self._dispatch("jm", event):
            yield result

    async def _dispatch(self, name: str, event: AstrMessageEvent):
        """把指令分发到指定模块

        Args:
            name: 模块名称。
            event: 消息事件。

        Yields:
            模块返回的消息结果。
        """
        module = self._manager.get_module(name)
        if not module:
            yield event.plain_result(f"× 模块「{name}」未启用")
            return

        args = self._parse_args(event, name)
        async for result in module.handle_command(name, args, event):
            yield result

    @staticmethod
    def _parse_args(event: AstrMessageEvent, command: str) -> list[str]:
        """解析指令参数

        AstrBot 的唤醒检查会剥离唤醒前缀，因此这里只需去掉指令名本身。

        Args:
            event: 消息事件。
            command: 指令名称。

        Returns:
            参数列表。
        """
        parts = event.get_message_str().strip().split()

        if parts and parts[0].lower() == command.lower():
            parts = parts[1:]

        return parts

    def _help_text(self) -> str:
        """生成帮助文本

        Returns:
            帮助信息文本。
        """
        lines = [
            f"▤ 资源查询插件 v{get_current_version()}",
            "────────────────",
            "用法:",
        ]

        for module in self._manager.get_all_modules():
            for cmd in module.get_commands():
                lines.append(f"  /{cmd['name']} — {cmd['desc']}")

        return "\n".join(lines)
