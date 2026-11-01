# MiMo 模块工具与默认配置
#
# 默认值统一来自 defaults.py，脚本内不写默认值。

from __future__ import annotations

from .defaults import DEFAULT_DEVICE_ID, DEFAULT_UA


def fmt_num(value) -> str:
    # 格式化数字：大数用万/亿简化
    try:
        if isinstance(value, str):
            # 已经是格式化过的字符串
            if any(c in value for c in ("万", "亿", ",")):
                return value
            value = float(value) if "." in value else int(value)
        number = int(value or 0)
    except (TypeError, ValueError):
        return str(value) if value else "0"

    if number >= 100_000_000:
        return f"{number / 100_000_000:.1f}亿"
    if number >= 10_000:
        return f"{number / 10_000:.1f}万"
    return str(number)


def get_default_device_id() -> str:
    # 获取默认设备标识
    return DEFAULT_DEVICE_ID


def get_default_ua() -> str:
    # 获取默认 User-Agent
    return DEFAULT_UA