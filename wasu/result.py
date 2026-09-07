"""华数广电查询结果类"""

from ..base import QueryResult
from .constants import DEFAULT_TEMPLATE


class WasuResult(QueryResult):
    """华数广电查询结果"""

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
            platform="华数广电",
            account_name=account_name,
            data=data,
            error=error,
        )
        self.template = template

    def _format_data(self) -> str:
        """格式化华数广电查询结果"""
        data = self.data

        # 如果有模板，使用模板格式化
        if self.template:
            try:
                # 提取流量详细信息
                traffic_items = data.get("traffic", {}).get("items", [])
                traffic_detail = ""
                for item in traffic_items:
                    tag = "结转" if item.get("is_carry") else ""
                    traffic_detail += f"\n     · {item['name']} {tag}: {item['total']} (已用 {item['used']} / 剩 {item['remain']})"

                # 提取语音信息
                voice_items = data.get("voice", [])
                voice_detail = ""
                for item in voice_items:
                    voice_detail += f"\n📞 语音: {item['name']}: {item['total']}分钟 | 剩余 {item['remain']}分钟"

                return self.template.format(
                    label=self.account_name,
                    balance=data.get("balance", {}).get("balance", "?"),
                    month_fee=data.get("balance", {}).get("month_fee", "?"),
                    arrears=data.get("balance", {}).get("arrears", "?"),
                    total_used=data.get("traffic", {}).get("total_used", "?"),
                    total=data.get("traffic", {}).get("total", "?"),
                    used=data.get("traffic", {}).get("used", "?"),
                    remain=data.get("traffic", {}).get("remain", "?"),
                    query_time=data.get("query_time", ""),
                    traffic_detail=traffic_detail,
                    voice_detail=voice_detail,
                )
            except (KeyError, ValueError):
                pass

        # 使用默认格式
        tpl = self.template or DEFAULT_TEMPLATE
        return tpl.format(
            label=self.account_name,
            balance=data.get("balance", {}).get("balance", "?"),
            month_fee=data.get("balance", {}).get("month_fee", "?"),
            arrears=data.get("balance", {}).get("arrears", "?"),
            total_used=data.get("traffic", {}).get("total_used", "?"),
            total=data.get("traffic", {}).get("total", "?"),
            used=data.get("traffic", {}).get("used", "?"),
            remain=data.get("traffic", {}).get("remain", "?"),
            query_time=data.get("query_time", ""),
        )
