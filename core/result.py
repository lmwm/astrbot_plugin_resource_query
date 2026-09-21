"""查询结果基类

统一各平台的查询结果渲染流程：
子类只需实现 `build_variables()`，模板渲染、空模板判断与异常兜底
都由基类完成，避免每个平台重复实现一遍格式化逻辑。

模板的来源由调用方决定（账号自定义模板或模块默认模板），
基类不负责查找模板。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class QueryResult(ABC):
    """查询结果统一格式

    Attributes:
        success: 是否查询成功。
        platform: 平台标识，用于日志与兜底提示。
        account_name: 账号显示名称。
        data: 查询数据。
        error: 错误信息，仅在 success 为 False 时有意义。
        template: 消息模板，由调用方提供。
    """

    success: bool
    platform: str
    account_name: str
    data: dict = field(default_factory=dict)
    error: str = ""
    template: str | None = None

    def to_text(self) -> str:
        """渲染为可直接发送的文本

        Returns:
            查询成功时为模板渲染结果；失败时为错误提示文本。
        """
        if not self.success:
            return f"{self.account_name}\n❌ {self.error or '查询失败'}"

        if not self.template:
            return f"{self.account_name}\n❌ 错误：模板未配置"

        try:
            return self.template.format(**self.build_variables())
        except Exception as e:
            logger.error(f"[{self.platform}] 模板渲染失败: {type(e).__name__}: {e}")
            return f"{self.account_name}\n❌ 格式化错误: {e}"

    @abstractmethod
    def build_variables(self) -> dict[str, str]:
        """构建模板变量

        Returns:
            变量名到字符串值的映射，用于填充 template。
        """
        raise NotImplementedError
