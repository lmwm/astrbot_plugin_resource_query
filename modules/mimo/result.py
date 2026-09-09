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
        bal = self.data.get("balance", {}).get("data", {})
        usage = self.data.get("usage", {}).get("data", {})
        tok = usage.get("tokenUsage", {})
        cost = usage.get("costUsage", {})
        limit = usage.get("accountRateLimit", {})

        tpm = int(limit.get("tpm") or 0)
        rpm = int(limit.get("rpm") or 0)
        concurrency = limit.get("concurrency")

        tpl = self.template or get_config_value("template.default", "")
        return tpl.format(
            label=self.account_name or "MiMo用量",
            balance=bal.get("balance", "?"),
            gift_balance=bal.get("giftBalance", "?"),
            input_token=fmt_num(tok.get("inputToken", 0)),
            output_token=fmt_num(tok.get("outputToken", 0)),
            cache_token=fmt_num(tok.get("cacheToken", 0)),
            monthly_cost=cost.get("currentMonthCost", "?"),
            total_cost=cost.get("totalCost", "?"),
            tpm=fmt_num(tpm),
            rpm=fmt_num(rpm),
            concurrency=concurrency or "-",
        )
