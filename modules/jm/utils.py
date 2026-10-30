# JMComic 模块工具与默认配置
#
# 默认值与 Views 配置项定义统一来自 `modules/jm/config.yaml`（只读），
# 修改该文件即可调整默认行为，且不会覆盖用户已保存的配置。

from __future__ import annotations

import re
from pathlib import Path

from ...common.module_config import load_defaults, load_fields

_MODULE_DIR = Path(__file__).parent
_CONFIG_FILE = _MODULE_DIR / "config.yaml"

# 中文字符匹配（用于判断简短名是否适合作为展示名）
CN_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def pick_display_name(oname: str, fallback: str) -> str:
    # 选择展示名称：优先使用含中文的简短名
    #
    #     站点提供的 oname（原始名）通常更简洁，但可能是日文/英文；
    #     只有在它非空且包含中文时才采用，否则退回完整标题。
    preferred = str(oname or "").strip()
    if preferred and CN_CHAR_PATTERN.search(preferred):
        return preferred

    return str(fallback or "").strip()


def get_default_config() -> dict:
    # 模块默认配置（来自 config.yaml）
    return load_defaults(_CONFIG_FILE)


def get_config_fields() -> list[dict]:
    # Views 配置项定义（来自 config.yaml，键顺序即显示顺序）
    return load_fields(_CONFIG_FILE)


def normalize_album_id(raw: str) -> int | None:
    # 标准化漫画 ID
    if not raw:
        return None

    text = str(raw).strip()

    if text.isdigit():
        return int(text)

    # JM+数字（允许 JM 与数字之间有空格，如 "JM 181251"）
    match = re.match(r"^[Jj][Mm]?\s*(\d+)$", text)
    if match:
        return int(match.group(1))

    # URL 形式
    for pattern in (r"/photo/(\d+)", r"/album/(\d+)"):
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))

    return None
