"""JMComic 模块工具函数"""

import re


def normalize_album_id(raw: str) -> int | None:
    """标准化漫画 ID

    Args:
        raw: 原始输入，可能是纯数字、JM+数字、URL 等。

    Returns:
        标准化的数字 ID，无效输入返回 None。
    """
    if not raw:
        return None

    # 移除空白
    raw = raw.strip()

    # 尝试直接解析数字
    if raw.isdigit():
        return int(raw)

    # 尝试从 JM+数字 格式提取
    match = re.match(r"^[Jj][Mm]?(\d+)$", raw)
    if match:
        return int(match.group(1))

    # 尝试从 URL 提取
    match = re.search(r"/photo/(\d+)", raw)
    if match:
        return int(match.group(1))

    match = re.search(r"/album/(\d+)", raw)
    if match:
        return int(match.group(1))

    return None
