"""MiMo 查询结果类"""

import logging

from ...base import QueryResult

logger = logging.getLogger(__name__)


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
        try:
            logger.info(f"[MiMoResult] 开始格式化, data keys: {list(self.data.keys())}")

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

            logger.info(f"[MiMoResult] tok: {tok}")
            logger.info(f"[MiMoResult] cost: {cost}")

            # 获取数值并转换为字符串
            def get_str(d, key, default="?"):
                val = d.get(key, default)
                if val is None:
                    return default
                return str(val)

            # 格式化大数字
            def fmt_num(n):
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

            # 准备变量
            variables = {
                "label": str(self.account_name or "MiMo用量"),
                "balance": get_str(balance_data, "balance"),
                "gift_balance": get_str(balance_data, "giftBalance"),
                "input_token": fmt_num(tok.get("inputToken", 0)),
                "output_token": fmt_num(tok.get("outputToken", 0)),
                "cache_token": fmt_num(tok.get("cacheToken", 0)),
                "monthly_cost": get_str(cost, "currentMonthCost"),
                "total_cost": get_str(cost, "totalCost"),
            }

            logger.info(f"[MiMoResult] variables: {variables}")

            # 获取模板（模板应该由调用方提供，不能为空）
            if not self.template:
                logger.error(f"[MiMoResult] 模板为空，无法格式化")
                return f"📋 {self.account_name}\n❌ 错误：模板未配置"
            tpl = self.template

            # 格式化
            result = tpl.format(**variables)
            logger.info(f"[MiMoResult] 格式化成功, 长度: {len(result)}")
            return result

        except Exception as e:
            logger.error(f"[MiMoResult] 错误: {type(e).__name__}: {e}")
            return f"📋 {self.account_name}\n❌ 格式化错误: {e}"
