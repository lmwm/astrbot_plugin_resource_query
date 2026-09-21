"""资源查询插件 - 基础框架"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """查询结果统一格式。

    Attributes:
        success: 是否查询成功。
        platform: 平台标识。
        account_name: 账号名称。
        data: 查询数据。
        error: 错误信息。
    """
    success: bool
    platform: str
    account_name: str
    data: dict
    error: str = ""

    def to_text(self) -> str:
        """将查询结果转换为可显示的文本格式。

        Returns:
            格式化后的文本。
        """
        if not self.success:
            return f"{self.platform} - {self.account_name}\n❌ {self.error}"
        return self._format_data()

    @abstractmethod
    def _format_data(self) -> str:
        """格式化查询数据（子类实现）。"""
        pass
