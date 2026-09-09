"""华数广电查询结果类"""

import logging

from ...base import QueryResult

logger = logging.getLogger(__name__)


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
        try:
            logger.info(f"[WasuResult] 开始格式化, data keys: {list(self.data.keys())}")

            # 获取模板（模板应该由调用方提供，不能为空）
            if not self.template:
                logger.error(f"[WasuResult] 模板为空，无法格式化")
                return f"📺 {self.account_name}\n❌ 错误：模板未配置"
            tpl = self.template

            data = self.data

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

            # 准备变量
            variables = {
                "label": str(self.account_name or "华数账号"),
                "balance": data.get("balance", {}).get("balance", "?"),
                "month_fee": data.get("balance", {}).get("month_fee", "?"),
                "arrears": data.get("balance", {}).get("arrears", "?"),
                "total_used": data.get("traffic", {}).get("total_used", "?"),
                "total": data.get("traffic", {}).get("total", "?"),
                "used": data.get("traffic", {}).get("used", "?"),
                "remain": data.get("traffic", {}).get("remain", "?"),
                "query_time": data.get("query_time", ""),
                "traffic_detail": traffic_detail,
                "voice_detail": voice_detail,
            }

            logger.info(f"[WasuResult] variables: {variables}")

            # 格式化
            result = tpl.format(**variables)
            logger.info(f"[WasuResult] 格式化成功, 长度: {len(result)}")
            return result

        except Exception as e:
            logger.error(f"[WasuResult] 错误: {type(e).__name__}: {e}")
            return f"📺 {self.account_name}\n❌ 格式化错误: {e}"
