# 通用工具层
#
# 提供与业务无关的基础能力：路径解析与 JSON/文本读写。

from .utils import (
    get_account_filename,
    get_config_path,
    get_data_path,
    get_platform_path,
    load_json_file,
    load_text_file,
    save_json_file,
    save_text_file,
)

__all__ = [
    "get_account_filename",
    "get_config_path",
    "get_data_path",
    "get_platform_path",
    "load_json_file",
    "load_text_file",
    "save_json_file",
    "save_text_file",
]