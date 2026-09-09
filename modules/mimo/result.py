"""MiMo 查询结果类"""

from ...base import QueryResult
from .utils import fmt_num, get_config_value


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
        """格式化 MiMo 查询结果"""
        # 兼容不同的数据结构
        # 结构1: {"balance": {"data": {...}}, "usage": {"data": {...}}}
        # 结构2: {"balance": {...}, "usage": {...}}
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
        limit = usage_data.get("accountRateLimit", {})

        # 安全获取数值
        def safe_get(d, key, default=0):
            val = d.get(key, default)
            if val is None:
                return default
            return val

        tpm = safe_get(limit, "tpm", 0)
        rpm = safe_get(limit, "rpm", 0)
        concurrency = limit.get("concurrency")

        tpl = self.template or get_config_value("template.default", "")
        return tpl.format(
            label=self.account_name or "MiMo用量",
            balance=safe_get(balance_data, "balance", "?"),
            gift_balance=safe_get(balance_data, "giftBalance", "?"),
            input_token=fmt_num(safe_get(tok, "inputToken", 0)),
            output_token=fmt_num(safe_get(tok, "outputToken", 0)),
            cache_token=fmt_num(safe_get(tok, "cacheToken", 0)),
            monthly_cost=safe_get(cost, "currentMonthCost", "?"),
            total_cost=safe_get(cost, "totalCost", "?"),
            tpm=fmt_num(tpm),
            rpm=fmt_num(rpm),
            concurrency=concurrency or "-",
        )
