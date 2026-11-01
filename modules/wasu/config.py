# 华数广电模块配置
#
# 账号表单字段、默认消息模板与变量说明都集中在这里；用户的改动保存在 plugin_data 的 config.json。

PLATFORM_NAME = "wasu"
PLATFORM_DISPLAY_NAME = "华数广电"

# 账号表单字段
ACCOUNT_FIELDS = [
    {"key": "name", "label": "账号名称", "type": "text", "hint": "留空则显示手机号"},
    {"key": "phone", "label": "手机号", "type": "text"},
    {"key": "user_key", "label": "User Key", "type": "text"},
    {"key": "token", "label": "Token", "type": "password", "hint": "失效后需重新获取"},
    {"key": "sign", "label": "Sign", "type": "password", "hint": "可选"},
]

# 默认消息模板
_TEMPLATE_LINES = [
    "{label}",
    "────────────────",
    "账户余额: {balance}",
    "   当月话费: {month_fee}",
    "   欠费: {arrears}",
    "",
    "本月累计使用: {total_used}",
    "   总流量: {total} | 已用: {used} | 剩余: {remain}",
    "",
    "查询时间: {query_time}",
]
DEFAULT_TEMPLATE = "\n".join(_TEMPLATE_LINES)

# 模板变量说明（Views 变量面板展示用）
VARIABLES = {
    "label": "账号名称",
    "balance": "账户余额",
    "month_fee": "当月话费",
    "arrears": "欠费",
    "total_used": "本月累计使用",
    "total": "总流量",
    "used": "已用流量",
    "remain": "剩余流量",
    "query_time": "查询时间",
    "traffic_detail": "流量明细（多行）",
    "voice_detail": "语音明细（多行）",
}