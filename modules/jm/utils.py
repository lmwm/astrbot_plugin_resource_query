"""JMComic 模块工具与默认配置

默认值与 Pages 配置项定义统一来自 `modules/jm/config.yaml`（只读），
修改该文件即可调整默认行为，且不会覆盖用户已保存的配置。
"""

from __future__ import annotations

import re
from pathlib import Path

from ...common.yaml_utils import get_config_value, load_yaml_config

_MODULE_DIR = Path(__file__).parent
_CONFIG_FILE = _MODULE_DIR / "config.yaml"

# 中文字符匹配（用于判断简短名是否适合作为展示名）
CN_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def pick_display_name(oname: str, fallback: str) -> str:
    """选择展示名称：优先使用含中文的简短名

    站点提供的 oname（原始名）通常更简洁，但可能是日文/英文；
    只有在它非空且包含中文时才采用，否则退回完整标题。

    Args:
        oname: 首选名称（原始名）。
        fallback: 回退名称（完整标题）。

    Returns:
        选中的名称（未做非法字符清洗）。
    """
    preferred = str(oname or "").strip()
    if preferred and CN_CHAR_PATTERN.search(preferred):
        return preferred

    return str(fallback or "").strip()

# config.yaml 缺失时的兜底默认值
_FALLBACK_DEFAULTS: dict = {
    "jm_enabled": True,
    "jm_send_file": True,
    "jm_show_info": False,
    "jm_max_file_size": 10,
    "jm_jpeg_quality": 75,
    "jm_max_concurrent": 1,
    "jm_image_threads": 16,
    "jm_photo_threads": 4,
    "jm_timeout": 20,
    "jm_retry_times": 3,
    "jm_proxy": "",
    "jm_cookies": "",
}

# config.yaml 缺失时的兜底字段定义
_FALLBACK_FIELDS: list[dict] = [
    {"key": "jm_enabled", "label": "启用下载功能", "type": "bool"},
    {"key": "jm_send_file", "label": "下载后发送 PDF", "type": "bool"},
    {"key": "jm_show_info", "label": "发送漫画信息", "type": "bool"},
    {"key": "jm_max_file_size", "label": "文件大小上限（MB）", "type": "int"},
]


def _config() -> dict:
    """加载模块 YAML 配置（结果带缓存）

    Returns:
        配置字典。
    """
    return load_yaml_config(_CONFIG_FILE)


def get_default_config() -> dict:
    """获取默认配置

    Returns:
        默认配置字典（config.yaml 中 defaults 段的副本）。
    """
    defaults = get_config_value(_config(), "defaults", None)
    if isinstance(defaults, dict) and defaults:
        return dict(defaults)
    return dict(_FALLBACK_DEFAULTS)


def get_config_fields() -> list[dict]:
    """获取 Pages 配置项定义

    以 config.yaml 中 fields 段的键顺序作为显示顺序，键名即配置键。

    Returns:
        字段定义列表。
    """
    raw = get_config_value(_config(), "fields", None)
    if not isinstance(raw, dict) or not raw:
        return [dict(item) for item in _FALLBACK_FIELDS]

    fields: list[dict] = []
    for key, meta in raw.items():
        item = {"key": key}
        if isinstance(meta, dict):
            item.update(meta)
        fields.append(item)

    return fields or [dict(item) for item in _FALLBACK_FIELDS]


def normalize_album_id(raw: str) -> int | None:
    """标准化漫画 ID

    Args:
        raw: 原始输入，可能是纯数字、JM+数字、URL 等。

    Returns:
        标准化的数字 ID，无效输入返回 None。
    """
    if not raw:
        return None

    text = str(raw).strip()

    if text.isdigit():
        return int(text)

    # JM+数字
    match = re.match(r"^[Jj][Mm]?(\d+)$", text)
    if match:
        return int(match.group(1))

    # URL 形式
    for pattern in (r"/photo/(\d+)", r"/album/(\d+)"):
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))

    return None
