"""通用工具模块"""

from .account import AccountManager
from .utils import get_data_path, get_config_path, get_platform_path

__all__ = [
    "AccountManager",
    "get_data_path",
    "get_config_path",
    "get_platform_path",
]
