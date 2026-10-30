# MiMo 模块工具与默认配置
#
# 默认值统一来自 `modules/mimo/config.yaml`（只读），脚本内不写默认值。

from __future__ import annotations

from pathlib import Path

from ...common.yaml_utils import get_config_value, load_yaml_config

_MODULE_DIR = Path(__file__).parent
_CONFIG_FILE = _MODULE_DIR / "config.yaml"


def _config() -> dict:
    # 加载模块 YAML 配置（结果带缓存）
    return load_yaml_config(_CONFIG_FILE)


def fmt_num(value) -> str:
    # 格式化数字：大数用万/亿简化
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
    # 获取默认设备标识
    return str(get_config_value(_config(), "device.default_device_id", "") or "")


def get_default_ua() -> str:
    # 获取默认 User-Agent
    return str(get_config_value(_config(), "device.default_ua", "") or "")


def get_default_template() -> str:
    # 获取默认消息模板
    return str(get_config_value(_config(), "template.default", "") or "")


def get_var_definitions() -> dict[str, str]:
    # 获取模板变量说明（Views 变量面板展示用）
    variables = get_config_value(_config(), "variables", None)
    if not isinstance(variables, dict):
        return {}

    return {str(key): str(value) for key, value in variables.items()}
