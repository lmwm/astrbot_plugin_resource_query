"""总管理器

协调各功能模块与 AstrBot 之间的通信：负责模块注册、账号汇总、
Pages schema 汇总与跨模块查询转发。

模块之间通过注册中心按名称取用，不直接互相依赖。
"""

from __future__ import annotations

from pathlib import Path

from .module import ModuleBase
from .registry import ModuleRegistry


class PluginManager:
    """总管理器

    Attributes:
        plugin_name: 插件名称。
        plugin_dir: 插件目录路径。
        registry: 模块注册中心。
    """

    def __init__(self, plugin_name: str, plugin_dir: Path) -> None:
        """初始化总管理器

        Args:
            plugin_name: 插件名称。
            plugin_dir: 插件目录路径。
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
    #  模块注册与访问
    # ══════════════════════════════════════════

    def register_module(self, module: ModuleBase) -> bool:
        """注册模块

        Args:
            module: 模块实例。

        Returns:
            是否注册成功；模块名重复时返回 False。
        """
        return self._registry.register(module)

    def get_module(self, module_name: str) -> ModuleBase | None:
        """获取模块实例

        Args:
            module_name: 模块名称。

        Returns:
            模块实例；不存在时返回 None。
        """
        return self._registry.get_module(module_name)

    def get_all_modules(self) -> list[ModuleBase]:
        """获取全部已注册模块

        Returns:
            模块实例列表（按注册顺序）。
        """
        return self._registry.get_all_modules()

    def get_module_names(self) -> list[str]:
        """获取全部已注册模块名称

        Returns:
            模块名称列表。
        """
        return self._registry.get_module_names()

    def has_module(self, module_name: str) -> bool:
        """判断模块是否已注册

        Args:
            module_name: 模块名称。

        Returns:
            是否已注册。
        """
        return self._registry.has_module(module_name)

    # ══════════════════════════════════════════
    #  账号汇总
    # ══════════════════════════════════════════

    def get_all_accounts(self) -> list[dict]:
        """汇总所有模块的账号

        Returns:
            账号列表；每项带 platform 字段标识所属模块。
        """
        accounts: list[dict] = []

        for module in self.get_all_modules():
            for acc in module.get_accounts():
                acc["platform"] = module.module_name
                accounts.append(acc)

        return accounts

    def delete_account(self, module_name: str, filename: str) -> dict | None:
        """删除指定模块的指定账号

        Args:
            module_name: 模块名称。
            filename: 账号配置文件名。

        Returns:
            被删除的账号数据；模块或账号不存在时返回 None。
        """
        module = self.get_module(module_name)
        if not module:
            return None
        return module.delete_account(filename)

    # ══════════════════════════════════════════
    #  Pages 支持
    # ══════════════════════════════════════════

    def get_page_schemas(self) -> list[dict]:
        """汇总各模块的 Pages 描述

        Returns:
            模块 schema 列表，供前端通用渲染配置页。
        """
        return [module.get_page_schema() for module in self.get_all_modules()]

    # ══════════════════════════════════════════
    #  查询转发
    # ══════════════════════════════════════════

    async def query_module(self, module_name: str, account: dict) -> dict:
        """查询指定模块的单个账号

        Args:
            module_name: 模块名称。
            account: 账号配置。

        Returns:
            查询结果字典。
        """
        module = self.get_module(module_name)
        if not module:
            return {"success": False, "account_name": "", "error": f"模块 {module_name} 不存在"}

        return await module.query(account)
