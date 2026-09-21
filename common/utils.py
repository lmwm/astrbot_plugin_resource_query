"""通用工具函数

只放与业务无关的通用能力：路径解析、JSON/文本文件读写、文件名规范化。
"""

from __future__ import annotations

import json
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path


def get_data_path(plugin_name: str) -> Path:
    """获取插件数据目录

    Args:
        plugin_name: 插件名称。

    Returns:
        插件数据目录路径（不存在时自动创建）。
    """
    data_path = Path(get_astrbot_data_path()) / "plugin_data" / plugin_name
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path


def get_config_path(plugin_name: str) -> Path:
    """获取插件配置根目录

    Args:
        plugin_name: 插件名称。

    Returns:
        配置根目录路径（不存在时自动创建）。
    """
    config_path = get_data_path(plugin_name) / "config"
    config_path.mkdir(parents=True, exist_ok=True)
    return config_path


def get_platform_path(plugin_name: str, platform: str) -> Path:
    """获取指定模块（平台）的配置目录

    Args:
        plugin_name: 插件名称。
        platform: 模块名称。

    Returns:
        模块配置目录路径（不存在时自动创建）。
    """
    platform_path = get_config_path(plugin_name) / platform
    platform_path.mkdir(parents=True, exist_ok=True)
    return platform_path


def get_account_filename(acc: dict, prefix: str = "") -> str:
    """根据账号信息生成配置文件名

    文件名来源优先级：name → account → phone → unnamed，
    并过滤掉文件系统不允许的字符。

    Args:
        acc: 账号配置字典。
        prefix: 文件名前缀，如 "mimo_"。

    Returns:
        形如 `<prefix><名称>.json` 的文件名。
    """
    name = str(acc.get("name", "") or "").strip()
    if not name:
        name = str(acc.get("account") or acc.get("phone") or "unnamed").strip()

    # 只保留字母、数字、横线、下划线与中文
    name = "".join(c for c in name if c.isalnum() or c in "-_\u4e00-\u9fff")
    if not name:
        name = "unnamed"

    return f"{prefix}{name}.json"


def load_json_file(file_path: Path) -> dict | None:
    """读取 JSON 文件

    Args:
        file_path: 文件路径。

    Returns:
        解析后的字典；失败返回 None。
    """
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_json_file(file_path: Path, data: dict) -> bool:
    """写入 JSON 文件

    Args:
        file_path: 文件路径。
        data: 要写入的数据。

    Returns:
        是否写入成功。
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def load_text_file(file_path: Path) -> str | None:
    """读取文本文件

    Args:
        file_path: 文件路径。

    Returns:
        文件内容；失败返回 None。
    """
    try:
        return file_path.read_text(encoding="utf-8")
    except OSError:
        return None


def save_text_file(file_path: Path, content: str) -> bool:
    """写入文本文件

    Args:
        file_path: 文件路径。
        content: 要写入的内容。

    Returns:
        是否写入成功。
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False
