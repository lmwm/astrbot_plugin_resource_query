"""核心框架层

提供模块化的基础设施：
- ModuleBase: 模块基类，所有功能模块必须继承
- ModuleRegistry: 模块注册中心，管理所有已注册的模块
- PluginManager: 总管理器，协调模块与 AstrBot 之间的通信
"""

from .module import ModuleBase
from .registry import ModuleRegistry
from .manager import PluginManager

__all__ = [
    "ModuleBase",
    "ModuleRegistry",
    "PluginManager",
]
