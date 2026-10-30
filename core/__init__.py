# 核心框架层
#
# - ModuleBase：功能模块基类
# - ModuleRegistry：模块注册中心
# - QueryResult：查询结果基类，统一模板渲染
# - GlobalWebApi：Views 全局接口
# - commands：指令参数解析与帮助文本

from .commands import help_text, parse_args
from .module import ModuleBase
from .registry import ModuleRegistry
from .result import QueryResult
from .web import GlobalWebApi

__all__ = [
    "GlobalWebApi",
    "ModuleBase",
    "ModuleRegistry",
    "QueryResult",
    "help_text",
    "parse_args",
]
