"""通用工具层

提供与业务无关的基础能力：
- 路径解析与 JSON/文本读写（utils）
- 简易 YAML 解析（yaml_utils）
"""

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
from .yaml_utils import get_config_value, load_yaml_config, parse_yaml

__all__ = [
    "get_data_path",
    "get_config_path",
    "get_platform_path",
    "get_account_filename",
    "load_json_file",
    "save_json_file",
    "load_text_file",
    "save_text_file",
    "parse_yaml",
    "load_yaml_config",
    "get_config_value",
]
