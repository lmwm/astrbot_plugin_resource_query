"""通用工具函数"""

import json
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path


def get_data_path(plugin_name: str) -> Path:
    """获取插件数据目录

    Args:
        plugin_name: 插件名称。

    Returns:
        插件数据目录路径。
    """
    data_path = Path(get_astrbot_data_path()) / "plugin_data" / plugin_name
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path


def get_config_path(plugin_name: str) -> Path:
    """获取配置根目录

    Args:
        plugin_name: 插件名称。

    Returns:
        配置根目录路径。
    """
    config_path = get_data_path(plugin_name) / "config"
    config_path.mkdir(parents=True, exist_ok=True)
    return config_path


def get_platform_path(plugin_name: str, platform: str) -> Path:
    """获取指定平台的配置目录

    Args:
        plugin_name: 插件名称。
        platform: 平台名称。

    Returns:
        平台配置目录路径。
    """
    platform_path = get_config_path(plugin_name) / platform
    platform_path.mkdir(parents=True, exist_ok=True)
    return platform_path


def get_account_filename(acc: dict) -> str:
    """获取账号配置文件名（格式：名称.json）

    Args:
        acc: 账号配置字典。

    Returns:
        配置文件名。
    """
    name = acc.get("name", "").strip()
    if not name:
        # 使用账号或手机号作为名称
        name = acc.get("account") or acc.get("phone") or "unnamed"
    # 清理文件名中的非法字符
    name = "".join(c for c in name if c.isalnum() or c in "-_\u4e00-\u9fff")
    if not name:
        name = "unnamed"
    return f"{name}.json"


def load_json_file(file_path: Path) -> dict | None:
    """加载 JSON 文件

    Args:
        file_path: 文件路径。

    Returns:
        解析后的字典，失败返回 None。
    """
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_json_file(file_path: Path, data: dict) -> bool:
    """保存 JSON 文件

    Args:
        file_path: 文件路径。
        data: 要保存的数据。

    Returns:
        是否保存成功。
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
    """加载文本文件

    Args:
        file_path: 文件路径。

    Returns:
        文件内容，失败返回 None。
    """
    try:
        return file_path.read_text(encoding="utf-8")
    except OSError:
        return None


def save_text_file(file_path: Path, content: str) -> bool:
    """保存文本文件

    Args:
        file_path: 文件路径。
        content: 要保存的内容。

    Returns:
        是否保存成功。
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False
