# 插件更新模块配置
#
# 模块设置字段、消息模板、变量说明与示例都在这里；用户的改动保存在 plugin_data 的 config.json。
# 消息模板用 {变量} 占位，每个模板可用的变量写在字段的 variables 里（Views 据此过滤标签）。

# 消息模板的默认内容（按行拼接，便于阅读）
_CHECKING_LINES = [
    "正在检查更新...",
    "  当前版本: v{current}",
    "  commit: {current_sha7}",
]
_FOUND_LINES = [
    "正在安装...",
    "  最新版本 v{latest}",
]
_DONE_LINES = [
    "更新完成",
    "  当前版本 v{current}",
    "  commit: {sha7}",
]
_ERROR_LINES = [
    "更新失败: ",
    "  {error}",
]

# 配置字段（key -> label / type / hint / group / variables / default）
CONFIG_FIELDS = {
    "proxy": {
        "label": "GitHub 代理",
        "type": "text",
        "hint": "如 https://gh-proxy.com/，留空使用默认代理",
        "default": "https://gh-proxy.com/",
    },
    "max_retries": {
        "label": "请求重试次数",
        "type": "int",
        "hint": "网络请求失败时的重试次数",
        "default": 3,
    },
    "force_update": {
        "label": "强制更新",
        "type": "bool",
        "hint": "手动 /query update 时忽略版本判断，总是重装；自动更新始终按版本判断",
        "default": True,
    },
    "schedule_enabled": {
        "label": "启用自动更新",
        "type": "bool",
        "hint": "按下面的表达式自动检查，有新版本才更新",
        "default": True,
    },
    "schedule_cron": {
        "label": "自动更新表达式（cron）",
        "type": "text",
        "hint": "五段式，例如 0 4 * * * 表示每天 04:00",
        "default": "0 4 * * *",
    },
    "message_checking": {
        "label": "检查中提示",
        "type": "template",
        "group": "messages",
        "hint": "变量 {current} {latest} {current_sha7} {sha7}",
        "default": "\n".join(_CHECKING_LINES),
        "variables": ["current", "latest", "current_sha", "current_sha7", "sha", "sha7"],
    },
    "message_found": {
        "label": "发现新版本提示",
        "type": "template",
        "group": "messages",
        "hint": "变量 {latest} {current} {sha7}",
        "default": "\n".join(_FOUND_LINES),
        "variables": ["current", "latest", "current_sha", "current_sha7", "sha", "sha7"],
    },
    "message_done": {
        "label": "更新完成消息",
        "type": "template",
        "group": "messages",
        "hint": "变量 {current} {latest} {current_sha7} {sha7} {elapsed}",
        "default": "\n".join(_DONE_LINES),
        "variables": [
            "current",
            "latest",
            "current_sha",
            "current_sha7",
            "sha",
            "sha7",
            "elapsed",
        ],
    },
    "message_skip": {
        "label": "已是最新提示",
        "type": "template",
        "group": "messages",
        "hint": "变量 {current} {latest}",
        "default": "当前已是最新版本 v{current}",
        "variables": ["current", "latest", "current_sha", "current_sha7", "sha", "sha7"],
    },
    "message_error": {
        "label": "失败消息",
        "type": "template",
        "group": "messages",
        "hint": "变量 {error} {current}",
        "default": "\n".join(_ERROR_LINES),
        "variables": ["current", "error"],
    },
}

# 配置分组：消息模板单独一页
CONFIG_GROUPS = [
    {
        "key": "messages",
        "label": "消息模板",
    },
]

# 消息模板变量（变量配置页与标签使用）
VARIABLES = {
    "current": "当前版本",
    "latest": "远端版本",
    "current_sha": "当前版本提交号",
    "current_sha7": "当前版本短提交号",
    "sha": "远端提交号",
    "sha7": "远端短提交号",
    "elapsed": "耗时（秒）",
    "error": "错误信息",
}

# 变量示例值，供模板预览使用
VAR_SAMPLES = {
    "current": "6.0.2",
    "latest": "6.0.3",
    "current_sha": "1101942f2ee9b12772ae7e6372794b1d09d8d57",
    "current_sha7": "1101942",
    "sha": "2c54e39abcdef0123456789abcdef0123456789",
    "sha7": "2c54e39",
    "elapsed": "5.2",
    "error": "网络连接超时",
}