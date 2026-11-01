# 华数广电模块工具
#
# 默认值统一来自 config.py，脚本内不写默认值。

from __future__ import annotations


def fmt_gb(value) -> str:
    # 把接口返回的 KB 数值格式化为 GB 字符串
    return f"{int(value or 0) / 1024 / 1024:.2f} GB"


def fmt_yuan(value) -> str:
    # 把接口返回的「分」格式化为「元」字符串
    return f"¥{int(value or 0) / 100:.2f}"