"""华数广电平台工具函数"""


def fmt_gb(val) -> str:
    """格式化流量为 GB"""
    return f"{int(val) / 1024 / 1024:.2f} GB"


def fmt_yuan(val) -> str:
    """格式化金额为元"""
    return f"¥{int(val) / 100:.2f}"
