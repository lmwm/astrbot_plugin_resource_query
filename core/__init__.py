"""核心框架层

- ModuleBase：功能模块基类，统一模块契约
- ModuleRegistry：模块注册中心
- PluginManager：总管理器，协调模块与 AstrBot 的通信
- QueryResult：查询结果基类，统一模板渲染
"""

from .manager import PluginManager
from .module import ModuleBase
from .registry import ModuleRegistry
from .result import QueryResult

__all__ = [
    "ModuleBase",
    "ModuleRegistry",
    "PluginManager",
    "QueryResult",
]
