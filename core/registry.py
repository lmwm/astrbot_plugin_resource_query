"""模块注册中心

负责管理所有已注册的模块，提供模块发现和访问功能。

设计原则：
1. 模块注册：模块启动时自动注册到注册中心
2. 模块发现：通过注册中心发现和访问其他模块
3. 模块隔离：注册中心不参与模块间的直接通信
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .module import ModuleBase


class ModuleRegistry:
    """模块注册中心

    管理所有已注册的模块，提供模块发现和访问功能。

    Attributes:
        _modules: 已注册的模块字典，key 为模块名称
    """

    def __init__(self):
        """初始化模块注册中心"""
        self._modules: dict[str, ModuleBase] = {}

    def register(self, module: ModuleBase) -> bool:
        """注册模块

        Args:
            module: 要注册的模块实例

        Returns:
            是否注册成功（如果模块名已存在则失败）
        """
        if module.module_name in self._modules:
            return False

        self._modules[module.module_name] = module
        module.set_registry(self)
        return True

    def unregister(self, module_name: str) -> bool:
        """注销模块

        Args:
            module_name: 要注销的模块名称

        Returns:
            是否注销成功
        """
        if module_name not in self._modules:
            return False

        module = self._modules.pop(module_name)
        module.set_registry(None)
        return True

    def get_module(self, module_name: str) -> ModuleBase | None:
        """获取模块实例

        Args:
            module_name: 模块名称

        Returns:
            模块实例，如果不存在则返回 None
        """
        return self._modules.get(module_name)

    def get_all_modules(self) -> list[ModuleBase]:
        """获取所有已注册的模块

        Returns:
            模块实例列表
        """
        return list(self._modules.values())

    def get_module_names(self) -> list[str]:
        """获取所有已注册的模块名称

        Returns:
            模块名称列表
        """
        return list(self._modules.keys())

    def has_module(self, module_name: str) -> bool:
        """检查模块是否已注册

        Args:
            module_name: 模块名称

        Returns:
            是否已注册
        """
        return module_name in self._modules
