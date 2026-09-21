"""华数广电查询结果

模板变量覆盖余额、话费、流量与语音明细。
"""

from __future__ import annotations

from ...core.result import QueryResult


class WasuResult(QueryResult):
    """华数广电查询结果"""

    def __init__(
        self,
        success: bool,
        account_name: str,
        data: dict | None = None,
        error: str = "",
        template: str | None = None,
    ) -> None:
        """初始化查询结果

        Args:
            success: 是否查询成功。
            account_name: 账号显示名称。
            data: 查询数据。
            error: 错误信息。
            template: 消息模板。
        """
        super().__init__(
            success=success,
            platform="华数广电",
            account_name=account_name,
            data=data or {},
            error=error,
            template=template,
        )

    def build_variables(self) -> dict[str, str]:
        """构建华数模板变量

        Returns:
            模板变量字典。
        """
        data = self.data
        balance = data.get("balance") or {}
        traffic = data.get("traffic") or {}
        items = traffic.get("items") or []
        voice_items = data.get("voice") or []

        traffic_detail = "".join(
            "\n     · {name}{tag}: {total} (已用 {used} / 剩 {remain})".format(
                name=item.get("name", ""),
                tag=" 结转" if item.get("is_carry") else "",
                total=item.get("total", ""),
                used=item.get("used", ""),
                remain=item.get("remain", ""),
            )
            for item in items
        )
        voice_detail = "".join(
            "\n📞 语音: {name}: {total}分钟 | 剩余 {remain}分钟".format(
                name=item.get("name", ""),
                total=item.get("total", ""),
                remain=item.get("remain", ""),
            )
            for item in voice_items
        )

        return {
            "label": str(self.account_name or "华数账号"),
            "balance": str(balance.get("balance", "?")),
            "month_fee": str(balance.get("month_fee", "?")),
            "arrears": str(balance.get("arrears", "?")),
            "total_used": str(traffic.get("total_used", "?")),
            "total": str(traffic.get("total", "?")),
            "used": str(traffic.get("used", "?")),
            "remain": str(traffic.get("remain", "?")),
            "query_time": str(data.get("query_time", "")),
            "traffic_detail": traffic_detail,
            "voice_detail": voice_detail,
        }
