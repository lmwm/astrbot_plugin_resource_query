# 模块注册中心
#
# 负责管理所有已注册的模块，提供模块发现和访问功能。
#
# 设计原则：
# 1. 模块注册：模块启动时自动注册到注册中心
# 2. 模块发现：通过注册中心发现和访问其他模块
# 3. 模块隔离：注册中心不参与模块间的直接通信

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .module import ModuleBase


class ModuleRegistry:
    # 模块注册中心
    #
    #     管理所有已注册的模块，提供模块发现和访问功能。

    def __init__(self):
        # 初始化模块注册中心
        self._modules: dict[str, ModuleBase] = {}

    def register(self, module: ModuleBase) -> bool:
        # 注册模块
        if module.module_name in self._modules:
            return False

        self._modules[module.module_name] = module
        module.set_registry(self)
        return True

    def unregister(self, module_name: str) -> bool:
        # 注销模块
        if module_name not in self._modules:
            return False

        module = self._modules.pop(module_name)
        module.set_registry(None)
        return True

    def get_module(self, module_name: str) -> ModuleBase | None:
        # 获取模块实例
        return self._modules.get(module_name)

    def get_all_modules(self) -> list[ModuleBase]:
        # 获取所有已注册的模块
        return list(self._modules.values())

    def get_module_names(self) -> list[str]:
        # 获取所有已注册的模块名称
        return list(self._modules.keys())

    def has_module(self, module_name: str) -> bool:
        # 检查模块是否已注册
        return module_name in self._modules
