# MiMo 模块默认配置
#
# 平台设备默认值与默认消息模板；用户的改动保存在 plugin_data 的 config.json，
# 账号级配置保存在 config/<账号>.json。

PLATFORM_NAME = "mimo"
PLATFORM_DISPLAY_NAME = "MiMo"

# 默认设备标识与 User-Agent（登录、OTP 验证、查询共用）
DEFAULT_DEVICE_ID = "wb_MIQUERY000001"
DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 16; 23127PN0CC Build/BP2A.250605.031.A3; wv)"
)

# 默认消息模板
_TEMPLATE_LINES = [
    "{label}",
    "────────────────",
    "  余      额        {balance}元",
    "  赠      送        {gift_balance}元",
    "  输      入        {input_token}",
    "  输      出        {output_token}",
    "  缓      存        {cache_token}",
    "  本月费用       {monthly_cost}元",
    "  累计费用       {total_cost}元",
]
DEFAULT_TEMPLATE = "\n".join(_TEMPLATE_LINES)

# 模板变量说明（Views 变量面板展示用）
VARIABLES = {
    "label": "账号名称",
    "balance": "余额",
    "gift_balance": "赠送余额",
    "input_token": "输入 Token",
    "output_token": "输出 Token",
    "cache_token": "缓存 Token",
    "monthly_cost": "本月费用",
    "total_cost": "累计费用",
    "tpm": "TPM 限额",
    "rpm": "RPM 限额",
    "concurrency": "并发限额",
}