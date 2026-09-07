"""通用工具模块

提供公共的工具函数，供各模块使用。
"""

from .utils import (
    get_data_path,
    get_config_path,
    get_platform_path,
    load_json_file,
    save_json_file,
    load_text_file,
    save_text_file,
    get_account_filename,
)

__all__ = [
    "get_data_path",
    "get_config_path",
    "get_platform_path",
    "load_json_file",
    "save_json_file",
    "load_text_file",
    "save_text_file",
    "get_account_filename",
]
