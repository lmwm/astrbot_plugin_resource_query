"""MiMo 模块工具与默认配置

默认值统一来自 `modules/mimo/config.yaml`（只读），
代码中只保留 config.yaml 缺失时的兜底值。
"""

from __future__ import annotations

from pathlib import Path

from ...common.yaml_utils import get_config_value, load_yaml_config

_MODULE_DIR = Path(__file__).parent
_CONFIG_FILE = _MODULE_DIR / "config.yaml"

# config.yaml 缺失时的兜底值
_FALLBACK_DEVICE_ID = "wb_MIQUERY000001"
_FALLBACK_UA = "Mozilla/5.0 (Linux; Android 16; 23127PN0CC Build/BP2A.250605.031.A3; wv)"
_FALLBACK_TEMPLATE = "{label}\n  余额: {balance}元\n  赠送: {gift_balance}元"


def _config() -> dict:
    """加载模块 YAML 配置（结果带缓存）

    Returns:
        配置字典。
    """
    return load_yaml_config(_CONFIG_FILE)


def fmt_num(value) -> str:
    """格式化数字：大数用万/亿简化

    Args:
        value: 数字或已格式化的字符串（如 "10.3亿"）。

    Returns:
        格式化后的字符串。
    """
    try:
        if isinstance(value, str):
            # 已经是格式化过的字符串
            if any(c in value for c in ("万", "亿", ",")):
                return value
            value = float(value) if "." in value else int(value)
        number = int(value or 0)
    except (TypeError, ValueError):
        return str(value) if value else "0"

    if number >= 100_000_000:
        return f"{number / 100_000_000:.1f}亿"
    if number >= 10_000:
        return f"{number / 10_000:.1f}万"
    return str(number)


def get_default_device_id() -> str:
    """获取默认设备标识

    Returns:
        设备标识字符串。
    """
    return get_config_value(_config(), "device.default_device_id", _FALLBACK_DEVICE_ID)


def get_default_ua() -> str:
    """获取默认 User-Agent

    Returns:
        User-Agent 字符串。
    """
    return get_config_value(_config(), "device.default_ua", _FALLBACK_UA)


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
