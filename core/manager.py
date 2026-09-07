"""总管理器基类

负责协调模块与 AstrBot 之间的通信。

设计原则：
1. 统一入口：所有 AstrBot 的请求通过总管理器分发
2. 模块协调：总管理器协调模块之间的通信
3. 配置管理：总管理器管理全局配置，模块配置由模块自治
"""

from pathlib import Path
from typing import Any

from .module import ModuleBase
from .registry import ModuleRegistry


class PluginManager:
    """总管理器基类

    协调模块与 AstrBot 之间的通信。

    Attributes:
        plugin_name: 插件名称
        plugin_dir: 插件目录路径
        registry: 模块注册中心
    """

    def __init__(self, plugin_name: str, plugin_dir: Path):
        """初始化总管理器

        Args:
            plugin_name: 插件名称
            plugin_dir: 插件目录路径
        """
        self._plugin_name = plugin_name
        self._plugin_dir = plugin_dir
        self._registry = ModuleRegistry()

    @property
    def plugin_name(self) -> str:
        """插件名称"""
        return self._plugin_name

    @property
    def plugin_dir(self) -> Path:
        """插件目录路径"""
        return self._plugin_dir

    @property
    def registry(self) -> ModuleRegistry:
        """模块注册中心"""
        return self._registry

    # ══════════════════════════════════════════
    #  模块管理
    # ══════════════════════════════════════════

    def register_module(self, module: ModuleBase) -> bool:
        """注册模块

        Args:
            module: 要注册的模块实例

        Returns:
            是否注册成功
        """
        return self._registry.register(module)

    def get_module(self, module_name: str) -> ModuleBase | None:
        """获取模块实例

        Args:
            module_name: 模块名称

        Returns:
            模块实例，如果不存在则返回 None
        """
        return self._registry.get_module(module_name)

    def get_all_modules(self) -> list[ModuleBase]:
        """获取所有已注册的模块

        Returns:
            模块实例列表
        """
        return self._registry.get_all_modules()

    def get_module_names(self) -> list[str]:
        """获取所有已注册的模块名称

        Returns:
            模块名称列表
        """
        return self._registry.get_module_names()

    # ══════════════════════════════════════════
    #  查询接口
    # ══════════════════════════════════════════

    async def query_module(self, module_name: str, account: dict) -> dict:
        """查询指定模块的账号

        Args:
            module_name: 模块名称
            account: 账号配置

        Returns:
            查询结果
        """
        module = self.get_module(module_name)
        if not module:
            return {
                "success": False,
                "error": f"模块 {module_name} 不存在"
            }

        return await module.query(account)

    async def query_all_module(self, module_name: str) -> list[dict]:
        """查询指定模块的所有账号

        Args:
            module_name: 模块名称

        Returns:
            查询结果列表
        """
        module = self.get_module(module_name)
        if not module:
            return [{
                "success": False,
                "error": f"模块 {module_name} 不存在"
            }]

        return await module.query_all()

    async def query_all(self) -> dict[str, list[dict]]:
        """查询所有模块的所有账号

        Returns:
            按模块分组的查询结果
        """
        results = {}
        for module in self.get_all_modules():
            results[module.module_name] = await module.query_all()
        return results

    # ══════════════════════════════════════════
    #  账号管理接口
    # ══════════════════════════════════════════

    def get_all_accounts(self) -> list[dict]:
        """获取所有模块的所有账号

        Returns:
            账号配置列表（包含 platform 字段）
        """
        accounts = []
        for module in self.get_all_modules():
            module_accounts = module.get_accounts()
            accounts.extend(module_accounts)
        return accounts

    def get_accounts_by_module(self, module_name: str) -> list[dict]:
        """获取指定模块的所有账号

        Args:
            module_name: 模块名称

        Returns:
            账号配置列表
        """
        module = self.get_module(module_name)
        if not module:
            return []
        return module.get_accounts()

    def delete_account(self, module_name: str, index: int) -> dict | None:
        """删除指定模块的指定账号

        Args:
            module_name: 模块名称
            index: 账号索引（从 0 开始）

        Returns:
            被删除的账号，如果模块不存在或索引无效则返回 None
        """
        module = self.get_module(module_name)
        if not module:
            return None
        return module.delete_account(index)

    # ══════════════════════════════════════════
    #  Web API 管理
    # ══════════════════════════════════════════

    def get_all_web_apis(self) -> list[dict]:
        """获取所有模块提供的 Web API 列表

        Returns:
            API 定义列表，每个 API 包含：
            - module: str, 所属模块名称
            - path: str, 完整 API 路径
            - handler: Callable, 处理函数
            - methods: list[str], HTTP 方法
            - desc: str, API 描述
        """
        apis = []
        for module in self.get_all_modules():
            module_apis = module.get_web_apis()
            for api in module_apis:
                api["module"] = module.module_name
                # 添加模块前缀到路径
                if not api["path"].startswith("/"):
                    api["path"] = f"/{module.module_name}/{api['path']}"
                apis.append(api)
        return apis

    # ══════════════════════════════════════════
    #  指令管理
    # ══════════════════════════════════════════

    def get_all_commands(self) -> list[dict]:
        """获取所有模块提供的指令列表

        Returns:
            指令定义列表
        """
        commands = []
        for module in self.get_all_modules():
            module_commands = module.get_commands()
            for cmd in module_commands:
                cmd["module"] = module.module_name
                commands.append(cmd)
        return commands

    async def handle_command(
        self,
        module_name: str,
        command: str,
        args: list[str],
        event: Any
    ) -> Any:
        """处理指令

        Args:
            module_name: 模块名称
            command: 指令名称
            args: 指令参数
            event: AstrBot 事件对象

        Returns:
            处理结果（生成器）
        """
        module = self.get_module(module_name)
        if not module:
            yield f"❌ 模块 {module_name} 不存在"
            return

        async for result in module.handle_command(command, args, event):
            yield result
