"""MiMo 平台工具函数"""

import json
from pathlib import Path

# 获取当前模块目录
_MODULE_DIR = Path(__file__).parent


def fmt_num(n) -> str:
    """格式化数字：大数用万/亿简化"""
    n = int(n or 0)
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return f"{n:,}"


def load_default_template(plugin_dir: Path | None = None) -> str:
    """加载默认模板，优先从模块目录读取"""
    # 优先从模块目录读取
    tpl_path = _MODULE_DIR / "default_template.txt"
    if tpl_path.exists():
        try:
            return tpl_path.read_text(encoding="utf-8")
        except OSError:
            pass

    # 兜底内置模板
    return """📋 {label}
────────────────
  余额        {balance}元
  赠送        {gift_balance}元
  输入        {input_token}
  输出        {output_token}
  缓存        {cache_token}
  本月费用    {monthly_cost}元
  累计费用    {total_cost}元"""


def load_config(plugin_dir: Path | None = None) -> dict:
    """加载默认配置，优先从模块目录读取"""
    default_config = {
        "platform": "mimo",
        "platform_name": "MiMo",
        "platform_icon": "📋",
        "default_device_id": "wb_MIQUERY000001",
        "default_ua": "APP/com.xiaomi.mihome APPV/11.3.203 iosPassportSDK/4.2.50 iOS/26.3.1",
        "api": {
            "account_base": "https://account.xiaomi.com",
            "balance_url": "https://platform.xiaomimimo.com/api/v1/balance",
            "usage_url": "https://platform.xiaomimimo.com/api/v1/usage",
        },
        "query_timeout": 15,
        "login_timeout": 15,
    }

    # 优先从模块目录读取
    config_path = _MODULE_DIR / "config.json"
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                file_config = json.load(f)
            # 合并配置，文件配置优先
            default_config.update(file_config)
        except (json.JSONDecodeError, OSError):
            pass

    return default_config
