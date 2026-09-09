"""MiMo 平台工具函数"""

import json
import re
from pathlib import Path

# 获取当前模块目录
_MODULE_DIR = Path(__file__).parent

# YAML 配置缓存
_yaml_config_cache: dict | None = None


def fmt_num(n) -> str:
    """格式化数字：大数用万/亿简化"""
    try:
        # 如果已经是格式化的字符串（如 "10.3亿"），直接返回
        if isinstance(n, str) and any(c in n for c in ['万', '亿', ',']):
            return n
        # 转换为数字
        if isinstance(n, str):
            n = float(n) if '.' in n else int(n)
        else:
            n = int(n) if n else 0
    except (ValueError, TypeError):
        return str(n) if n else "0"

    # 确保 n 是数字类型
    n = int(n)

    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def _convert_value(value: str):
    """将 YAML 值字符串转换为合适的 Python 类型

    Args:
        value: YAML 值字符串

    Returns:
        转换后的值（int、float、bool、None 或 str）
    """
    if not value:
        return ""
    # 布尔值
    if value.lower() in ("true", "yes", "on"):
        return True
    if value.lower() in ("false", "no", "off"):
        return False
    # null
    if value.lower() in ("null", "~"):
        return None
    # 整数
    try:
        return int(value)
    except ValueError:
        pass
    # 浮点数
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_yaml_simple(text: str) -> dict:
    """简单的 YAML 解析器（支持基本的键值对、嵌套和块标量）

    支持 |- / |+ / > 等块标量指示符。

    Args:
        text: YAML 文本内容

    Returns:
        解析后的字典
    """
    result = {}
    current_section = None
    current_subsection = None
    base_indent = 0

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        # 跳过空行和注释
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # 计算缩进级别
        indent = len(line) - len(line.lstrip())

        # 解析键值对（只在当前缩进级别解析）
        match = re.match(r"^(\w+):\s*(.*)?$", stripped)
        if match:
            key = match.group(1)
            value = match.group(2).strip() if match.group(2) else ""

            # 顶层键（缩进为0）
            if indent == 0:
                base_indent = 0
                current_section = key
                current_subsection = None

                if value:
                    # 移除引号
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    result[key] = _convert_value(value)
                else:
                    result[key] = {}
                i += 1
                continue

            # 子键（缩进大于0）
            if current_section and indent > base_indent:
                # 处理多行字符串（支持 |、|-、|+、>、>-、>+）
                if value and re.match(r'^[|>][+-]?$', value):
                    current_subsection = key
                    block_lines = []
                    # 记录块内容的基准缩进（取后续第一行的缩进）
                    block_base_indent = None
                    i += 1
                    while i < len(lines):
                        bline = lines[i]
                        bstripped = bline.strip()
                        # 空行保留
                        if not bstripped:
                            block_lines.append("")
                            i += 1
                            continue
                        bindent = len(bline) - len(bline.lstrip())
                        # 如果缩进小于等于父级键的缩进，块结束
                        if bindent <= indent:
                            break
                        if block_base_indent is None:
                            block_base_indent = bindent
                        # 去掉块基准缩进
                        content = bline[block_base_indent:] if block_base_indent else bstripped
                        block_lines.append(content)
                        i += 1
                    # 根据块标量类型决定连接方式
                    if value.startswith(">"):
                        # 折叠模式：空行分段，非空行用空格连接
                        paragraphs = []
                        current_para = []
                        for bl in block_lines:
                            if bl == "":
                                if current_para:
                                    paragraphs.append(" ".join(current_para))
                                    current_para = []
                            else:
                                current_para.append(bl)
                        if current_para:
                            paragraphs.append(" ".join(current_para))
                        result[current_section][key] = "\n".join(paragraphs)
                    else:
                        # 字面模式（|）：保留换行
                        result[current_section][key] = "\n".join(block_lines)
                    # 不递增 i，while 循环已经推进到了块结束位置
                    continue

                if value:
                    # 移除引号
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    result[current_section][key] = _convert_value(value)
                else:
                    current_subsection = key
                    result[current_section][key] = {}

        # 处理多行字符串内容（兼容旧的无块标量写法）
        elif current_subsection and current_section:
            if isinstance(result[current_section].get(current_subsection), str):
                if result[current_section][current_subsection]:
                    result[current_section][current_subsection] += "\n"
                result[current_section][current_subsection] += stripped

        i += 1

    return result


def load_yaml_config() -> dict:
    """加载 YAML 配置文件

    Returns:
        配置字典
    """
    global _yaml_config_cache

    if _yaml_config_cache is not None:
        return _yaml_config_cache

    yaml_path = _MODULE_DIR / "config.yaml"
    if yaml_path.exists():
        try:
            content = yaml_path.read_text(encoding="utf-8")
            _yaml_config_cache = _parse_yaml_simple(content)
            return _yaml_config_cache
        except (OSError, Exception):
            pass

    # 返回默认配置
    _yaml_config_cache = {
        "platform": {"name": "mimo", "display_name": "MiMo", "icon": "📋"},
        "api": {
            "account_base": "https://account.xiaomi.com",
            "balance_url": "https://platform.xiaomimimo.com/api/v1/balance",
            "usage_url": "https://platform.xiaomimimo.com/api/v1/usage",
        },
        "device": {
            "default_device_id": "wb_MIQUERY000001",
            "default_ua": "APP/com.xiaomi.mihome APPV/11.3.203 iosPassportSDK/4.2.50 iOS/26.3.1",
            "ua_otp": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
        },
        "timeout": {"query": 15, "login": 15},
        "template": {
            "default": "📋 {label}\n────────────────\n  余额        {balance}元\n  赠送        {gift_balance}元\n  输入        {input_token}\n  输出        {output_token}\n  缓存        {cache_token}\n  本月费用    {monthly_cost}元\n  累计费用    {total_cost}元"
        },
    }
    return _yaml_config_cache


def get_config_value(key_path: str, default=None):
    """获取配置值

    Args:
        key_path: 配置路径，如 "api.account_base" 或 "device.default_device_id"
        default: 默认值

    Returns:
        配置值
    """
    config = load_yaml_config()
    keys = key_path.split(".")
    value = config

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


def load_default_template(plugin_dir: Path | None = None) -> str:
    """加载默认模板，优先从 YAML 配置读取"""
    # 优先从 YAML 配置读取
    template = get_config_value("template.default")
    if template:
        return template

    # 兜底内置模板（最小化，仅包含必要字段）
    return "📋 {label}\n  余额: {balance}元\n  赠送: {gift_balance}元"


def load_config(plugin_dir: Path | None = None) -> dict:
    """加载配置，从 YAML 配置文件读取

    Returns:
        配置字典
    """
    yaml_config = load_yaml_config()

    # 转换为原有格式以保持兼容
    return {
        "platform": get_config_value("platform.name", "mimo"),
        "platform_name": get_config_value("platform.display_name", "MiMo"),
        "platform_icon": get_config_value("platform.icon", "📋"),
        "default_device_id": get_config_value("device.default_device_id", "wb_MIQUERY000001"),
        "default_ua": get_config_value("device.default_ua", ""),
        "api": {
            "account_base": get_config_value("api.account_base", "https://account.xiaomi.com"),
            "balance_url": get_config_value("api.balance_url", "https://platform.xiaomimimo.com/api/v1/balance"),
            "usage_url": get_config_value("api.usage_url", "https://platform.xiaomimimo.com/api/v1/usage"),
        },
        "query_timeout": get_config_value("timeout.query", 15),
        "login_timeout": get_config_value("timeout.login", 15),
    }
