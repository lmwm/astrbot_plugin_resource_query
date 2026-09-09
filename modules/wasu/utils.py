"""华数广电平台工具函数"""

import re
from pathlib import Path

# 获取当前模块目录
_MODULE_DIR = Path(__file__).parent

# YAML 配置缓存
_yaml_config_cache: dict | None = None


def _parse_yaml_simple(text: str) -> dict:
    """简单的 YAML 解析器（支持基本的键值对和嵌套）

    Args:
        text: YAML 文本内容

    Returns:
        解析后的字典
    """
    result = {}
    current_section = None
    current_subsection = None
    base_indent = 0

    for line in text.split("\n"):
        # 跳过空行和注释
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
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
                    result[key] = value
                else:
                    result[key] = {}
                continue

            # 子键（缩进大于0）
            if current_section and indent > base_indent:
                # 处理多行字符串
                if value == "|":
                    current_subsection = key
                    result[current_section][key] = ""
                    continue

                if value:
                    # 移除引号
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    result[current_section][key] = value
                else:
                    current_subsection = key
                    result[current_section][key] = {}

        # 处理多行字符串内容
        elif current_subsection and current_section:
            if isinstance(result[current_section].get(current_subsection), str):
                if result[current_section][current_subsection]:
                    result[current_section][current_subsection] += "\n"
                # 去掉前导空格，但保留相对缩进
                content_indent = len(line) - len(line.lstrip())
                result[current_section][current_subsection] += stripped

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
        "platform": {"name": "wasu", "display_name": "华数广电", "icon": "📺"},
        "api": {"base_url": "https://ups.wasu.cn"},
        "headers": {"user_agent": "Mozilla/5.0 (Linux; Android 16; 23127PN0CC Build/BP2A.250605.031.A3; wv) "},
        "timeout": {"query": 10},
        "template": {
            "default": "📺 {label}\n────────────────\n💰 账户余额: {balance}\n   当月话费: {month_fee}\n   欠费: {arrears}\n\n📶 本月累计使用: {total_used}\n   总流量: {total} | 已用: {used} | 剩余: {remain}\n\n🕐 查询时间: {query_time}"
        },
    }
    return _yaml_config_cache


def get_config_value(key_path: str, default=None):
    """获取配置值

    Args:
        key_path: 配置路径，如 "api.base_url" 或 "template.default"
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


def load_default_template() -> str:
    """加载默认模板，优先从 YAML 配置读取"""
    # 优先从 YAML 配置读取
    template = get_config_value("template.default")
    if template:
        return template

    # 兜底内置模板（最小化，仅包含必要字段）
    return "📺 {label}\n  余额: {balance}\n  话费: {month_fee}"


def fmt_gb(val) -> str:
    """格式化流量为 GB"""
    return f"{int(val) / 1024 / 1024:.2f} GB"


def fmt_yuan(val) -> str:
    """格式化金额为元"""
    return f"¥{int(val) / 100:.2f}"
