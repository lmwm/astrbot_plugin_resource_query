"""MiMo 平台常量 - 从 config.yaml 统一管理"""

from .utils import get_config_value

# 默认内置模板（从 YAML 配置读取）
DEFAULT_TEMPLATE = get_config_value(
    "template.default",
    "📋 {label}\n────────────────\n  余额        {balance}元\n  赠送        {gift_balance}元\n  输入        {input_token}\n  输出        {output_token}\n  缓存        {cache_token}\n  本月费用    {monthly_cost}元\n  累计费用    {total_cost}元"
)

# 默认 API 地址（从 YAML 配置读取）
DEFAULT_ACCOUNT_BASE = get_config_value("api.account_base", "https://account.xiaomi.com")
DEFAULT_BALANCE_URL = get_config_value("api.balance_url", "https://platform.xiaomimimo.com/api/v1/balance")
DEFAULT_USAGE_URL = get_config_value("api.usage_url", "https://platform.xiaomimimo.com/api/v1/usage")

# 默认设备配置（从 YAML 配置读取）
DEFAULT_DEVICE_ID = get_config_value("device.default_device_id", "wb_MIQUERY000001")
DEFAULT_UA = get_config_value("device.default_ua", "APP/com.xiaomi.mihome APPV/11.3.203 iosPassportSDK/4.2.50 iOS/26.3.1")
DEFAULT_UA_OTP = get_config_value("device.ua_otp", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")

# 超时设置（从 YAML 配置读取）
DEFAULT_QUERY_TIMEOUT = get_config_value("timeout.query", 15)
DEFAULT_LOGIN_TIMEOUT = get_config_value("timeout.login", 15)
