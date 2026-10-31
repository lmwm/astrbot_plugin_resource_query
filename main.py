# 资源查询插件入口
#
# 只做三件事：按 AstrBot 原生配置注册模块、注册 Views 接口、把指令分发到模块。
# 新增功能模块只需在 `modules/` 下实现 ModuleBase 并在 _MODULE_CLASSES 登记一行。

from __future__ import annotations

from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core.commands import help_text, parse_args
from .core.registry import ModuleRegistry
from .core.web import GlobalWebApi
from .modules import JMModule, MimoModule, UpdateModule, WasuModule
from .modules.update.updater import get_current_version

# 插件唯一标识
PLUGIN_NAME = "astrbot_plugin_resource_query"

# 功能模块清单：模块名 → 模块类；字典顺序即 Views 导航与帮助文本顺序
_MODULE_CLASSES: dict[str, type] = {
    "mimo": MimoModule,
    "wasu": WasuModule,
    "jm": JMModule,
    "update": UpdateModule,
}


class ResourceQueryPlugin(Star):
    # 资源查询插件

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        self._plugin_dir = Path(__file__).parent
        self._registry = ModuleRegistry()
        self._web = GlobalWebApi(self._registry, get_current_version)

        self._register_modules(context)
        self._register_web_apis(context)

    def _register_modules(self, context: Context) -> None:
        # 未显式配置时默认启用
        enabled = self.config.get("modules") or {}

        for name, module_cls in _MODULE_CLASSES.items():
            if not enabled.get(f"{name}_enabled", True):
                logger.info(f"[{PLUGIN_NAME}] 模块 {name} 已在配置中禁用，跳过加载")
                continue

            module = module_cls(self._plugin_dir, PLUGIN_NAME)
            module.set_context(context)

            if not self._registry.register(module):
                logger.warning(f"[{PLUGIN_NAME}] 模块 {name} 注册失败（名称重复）")

    def _register_web_apis(self, context: Context) -> None:
        for path, handler, methods, desc in self._web.routes():
            context.register_web_api(f"/{PLUGIN_NAME}/{path}", handler, methods, desc)

        # 模块自有接口的路径带模块名前缀
        for module in self._registry.get_all_modules():
            for api in module.get_web_apis():
                context.register_web_api(
                    f"/{PLUGIN_NAME}/{module.module_name}/{api['path']}",
                    api["handler"],
                    api.get("methods", ["GET"]),
                    api.get("desc", ""),
                )

    async def initialize(self) -> None:
        # AstrBot 加载插件后调用：让各模块做异步初始化（如注册定时任务）
        for module in self._registry.get_all_modules():
            await module.on_load()

    async def terminate(self) -> None:
        # 插件卸载/重载前调用：让各模块清理注册
        for module in self._registry.get_all_modules():
            await module.on_unload()

    @filter.command("query")
    async def query_cmd(self, event: AstrMessageEvent):
        # /query — 显示帮助，或分发 /query <模块名>
        args = parse_args(event, "query")

        if not args:
            yield event.plain_result(
                help_text(get_current_version(), self._registry.get_all_modules())
            )
            return

        name = args[0].lower()
        module = self._registry.get_module(name)

        if not module:
            enabled = "、".join(self._registry.get_module_names()) or "（无）"
            yield event.plain_result(f"× 未知功能: {name}\n已启用: {enabled}")
            return

        async for result in module.handle_command(name, args[1:], event):
            yield result

    @filter.command("mimo")
    async def mimo_cmd(self, event: AstrMessageEvent):
        async for result in self._dispatch("mimo", event):
            yield result

    @filter.command("wasu")
    async def wasu_cmd(self, event: AstrMessageEvent):
        async for result in self._dispatch("wasu", event):
            yield result

    @filter.command("jm", alias={"JM", "Jm", "jM"})
    async def jm_cmd(self, event: AstrMessageEvent):
        async for result in self._dispatch("jm", event):
            yield result

    async def _dispatch(self, name: str, event: AstrMessageEvent):
        module = self._registry.get_module(name)
        if not module:
            yield event.plain_result(f"× 模块「{name}」未启用")
            return

        args = parse_args(event, name)
        async for result in module.handle_command(name, args, event):
            yield result
