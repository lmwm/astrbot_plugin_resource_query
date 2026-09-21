"""MiMo 查询结果类"""

import logging

from ...base import QueryResult

logger = logging.getLogger(__name__)


def _get_str(d: dict, key: str, default: str = "?") -> str:
    """从字典中获取值并转为字符串。

    Args:
        d: 数据字典。
        key: 键名。
        default: 默认值。

    Returns:
        字符串形式的值。
    """
    val = d.get(key, default)
    return default if val is None else str(val)


def _fmt_num(n) -> str:
    """格式化数字，大数用万/亿简化。

    Args:
        n: 要格式化的数字或字符串。

    Returns:
        格式化后的字符串。
    """
    try:
        if isinstance(n, str):
            if any(c in n for c in ['万', '亿', ',']):
                return n
            n = int(float(n))
        else:
            n = int(n)
    except (ValueError, TypeError):
        return str(n)

    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


class MimoResult(QueryResult):
    """MiMo 查询结果"""

    def __init__(
        self,
        success: bool,
        account_name: str,
        data: dict,
        error: str = "",
        template: str | None = None,
    ):
        super().__init__(
            success=success,
            platform="MiMo",
            account_name=account_name,
            data=data,
            error=error,
        )
        self.template = template

    def _format_data(self) -> str:
        """格式化 MiMo 查询结果，将查询数据填充到模板中。

        Returns:
            格式化后的文本结果。

        Raises:
            无显式抛出，内部捕获所有异常并返回错误文本。
        """
        try:
            # 兼容不同的数据结构
            balance_data = self.data.get("balance", {})
            usage_data = self.data.get("usage", {})

            # 如果有嵌套的 data 属性，使用它
            if isinstance(balance_data, dict) and "data" in balance_data:
                balance_data = balance_data["data"]
            if isinstance(usage_data, dict) and "data" in usage_data:
                usage_data = usage_data["data"]

            # 获取各个字段
            tok = usage_data.get("tokenUsage", {})
            cost = usage_data.get("costUsage", {})

            # 准备变量
            variables = {
                "label": str(self.account_name or "MiMo用量"),
                "balance": _get_str(balance_data, "balance"),
                "gift_balance": _get_str(balance_data, "giftBalance"),
                "input_token": _fmt_num(tok.get("inputToken", 0)),
                "output_token": _fmt_num(tok.get("outputToken", 0)),
                "cache_token": _fmt_num(tok.get("cacheToken", 0)),
                "monthly_cost": _get_str(cost, "currentMonthCost"),
                "total_cost": _get_str(cost, "totalCost"),
            }

            # 获取模板（模板应该由调用方提供，不能为空）
            if not self.template:
                return f"{self.account_name}\n❌ 错误：模板未配置"

            # 格式化
            return self.template.format(**variables)

        except Exception as e:
            logger.error(f"[MiMoResult] 格式化错误: {type(e).__name__}: {e}")
            return f"{self.account_name}\n❌ 格式化错误: {e}"
