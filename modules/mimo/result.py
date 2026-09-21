"""MiMo 查询结果

模板变量覆盖余额、Token 用量、费用与限额（TPM / RPM / 并发），
与 `modules/mimo/config.yaml` 中的默认模板保持一致。
"""

from __future__ import annotations

from ...core.result import QueryResult
from .utils import fmt_num


def _get_str(data: dict, key: str, default: str = "?") -> str:
    """从字典取值并转为字符串

    Args:
        data: 数据字典。
        key: 键名。
        default: 缺失或为 None 时的默认值。

    Returns:
        字符串形式的值。
    """
    value = data.get(key, default)
    return default if value is None else str(value)


def _get_limit(limits: dict, key: str) -> str:
    """读取并格式化限额字段

    Args:
        limits: 限额数据字典（accountRateLimit）。
        key: 字段名，如 "tpm"。

    Returns:
        格式化后的字符串；字段缺失或为 0 时返回 "-"。
    """
    value = limits.get(key) if isinstance(limits, dict) else None
    if not value:
        return "-"
    return fmt_num(value)


class MimoResult(QueryResult):
    """MiMo 查询结果"""

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
            data: 查询数据（接口原始响应）。
            error: 错误信息。
            template: 消息模板。
        """
        super().__init__(
            success=success,
            platform="MiMo",
            account_name=account_name,
            data=data or {},
            error=error,
            template=template,
        )

    def build_variables(self) -> dict[str, str]:
        """构建 MiMo 模板变量

        Returns:
            模板变量字典。
        """
        balance_data = self.data.get("balance", {})
        usage_data = self.data.get("usage", {})

        # 兼容响应中嵌套一层 data 的情况
        if isinstance(balance_data, dict) and "data" in balance_data:
            balance_data = balance_data["data"]
        if isinstance(usage_data, dict) and "data" in usage_data:
            usage_data = usage_data["data"]

        token = usage_data.get("tokenUsage", {})
        cost = usage_data.get("costUsage", {})
        limit = usage_data.get("accountRateLimit", {})

        return {
            "label": str(self.account_name or "MiMo用量"),
            "balance": _get_str(balance_data, "balance"),
            "gift_balance": _get_str(balance_data, "giftBalance"),
            "input_token": fmt_num(token.get("inputToken", 0)),
            "output_token": fmt_num(token.get("outputToken", 0)),
            "cache_token": fmt_num(token.get("cacheToken", 0)),
            "monthly_cost": _get_str(cost, "currentMonthCost"),
            "total_cost": _get_str(cost, "totalCost"),
            "tpm": _get_limit(limit, "tpm"),
            "rpm": _get_limit(limit, "rpm"),
            "concurrency": _get_limit(limit, "concurrency"),
        }
