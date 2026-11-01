# MiMo 模块配置
#
# 账号表单字段、分组、默认设备值、默认消息模板与变量说明都集中在这里；
# 用户的改动保存在 plugin_data 的 config.json，账号级配置保存在 config/<账号>.json。

PLATFORM_NAME = "mimo"
PLATFORM_DISPLAY_NAME = "MiMo"

# 默认设备标识与 User-Agent（登录、OTP 验证、查询共用）
DEFAULT_DEVICE_ID = "wb_MIQUERY000001"
DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 16; 23127PN0CC Build/BP2A.250605.031.A3; wv)"
)

# 账号字段分组：三种凭据方式作为标签页，设备信息作为内联区块
ACCOUNT_GROUPS = [
    {
        "key": "password",
        "label": "账号密码登录",
        "mode": "tab",
        "hint": "输入小米账号与密码，首次登录可能需要短信验证码",
    },
    {
        "key": "passtoken",
        "label": "PassToken",
        "mode": "tab",
        "hint": "已有 PassToken 时使用，插件会自动换取 ServiceToken",
    },
    {
        "key": "servicetoken",
        "label": "ServiceToken",
        "mode": "tab",
        "hint": "直接使用 ServiceToken 查询，无需再次登录",
    },
    {
        "key": "device",
        "label": "设备信息（可选）",
        "mode": "inline",
        "hint": "留空时保存会自动填充插件默认值，可点字段右侧的「↺」单独恢复默认",
    },
]

# 账号表单字段；group 决定字段出现在哪个分组
ACCOUNT_FIELDS = [
    {"key": "name", "label": "账号名称", "type": "text", "hint": "留空则显示小米账号"},
    {
        "key": "account",
        "label": "小米账号",
        "type": "text",
        "group": "password",
        "hint": "手机号或邮箱",
    },
    {"key": "password", "label": "密码", "type": "password", "group": "password"},
    {
        "key": "userId",
        "label": "User ID",
        "type": "text",
        "group": ["passtoken", "servicetoken"],
        "hint": "登录后自动填充",
    },
    {
        "key": "passToken",
        "label": "PassToken",
        "type": "password",
        "group": "passtoken",
        "hint": "登录后自动填充",
    },
    {
        "key": "serviceToken",
        "label": "ServiceToken",
        "type": "password",
        "group": "servicetoken",
        "hint": "登录后自动填充",
    },
    {
        "key": "device_id",
        "label": "设备标识",
        "type": "text",
        "group": "device",
        "default": DEFAULT_DEVICE_ID,
    },
    {
        "key": "ua",
        "label": "User-Agent",
        "type": "text",
        "group": "device",
        "default": DEFAULT_UA,
    },
]

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