"""华数广电模块工具与默认配置

默认值统一来自 `modules/wasu/config.yaml`（只读）。
"""

from __future__ import annotations

from pathlib import Path

from ...common.yaml_utils import get_config_value, load_yaml_config

_MODULE_DIR = Path(__file__).parent
_CONFIG_FILE = _MODULE_DIR / "config.yaml"

# config.yaml 缺失时的兜底模板
_FALLBACK_TEMPLATE = "{label}\n  余额: {balance}\n  当月话费: {month_fee}"


def _config() -> dict:
    """加载模块 YAML 配置（结果带缓存）

    Returns:
        配置字典。
    """
    return load_yaml_config(_CONFIG_FILE)


def get_default_template() -> str:
    """获取默认消息模板

    Returns:
        默认模板文本。
    """
    return get_config_value(_config(), "template.default", _FALLBACK_TEMPLATE)


def get_var_definitions() -> dict[str, str]:
    """获取模板变量说明（Pages 变量面板展示用）

    Returns:
        变量名到中文描述的映射；config.yaml 未定义时返回空字典。
    """
    variables = get_config_value(_config(), "variables", None)
    if not isinstance(variables, dict):
        return {}

    return {str(key): str(value) for key, value in variables.items()}


def fmt_gb(value) -> str:
    """把接口返回的 KB 数值格式化为 GB 字符串

    Args:
        value: KB 数值。

    Returns:
        形如 "15.62 GB" 的字符串。
    """
    return f"{int(value or 0) / 1024 / 1024:.2f} GB"


def fmt_yuan(value) -> str:
    """把接口返回的「分」格式化为「元」字符串

    Args:
        value: 以分为单位的金额。

    Returns:
        形如 "¥56.80" 的字符串。
    """
    return f"¥{int(value or 0) / 100:.2f}"
