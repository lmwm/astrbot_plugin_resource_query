# 插件更新模块配置
#
# 模块设置字段、消息模板、变量说明与示例都在这里；用户的改动保存在 plugin_data 的 config.json。
# 消息模板用 {变量} 占位，每个模板可用的变量写在字段的 variables 里（Views 据此过滤标签）。

# 消息模板的默认内容（按行拼接，便于阅读）
_CHECKING_LINES = [
    "正在检查更新...",
]
_FOUND_LINES = [
    "版本: v{current} → v{latest}\n  commit: {latest_sha7}",
]
_DONE_LINES = [
    "更新完成...\n  当前版本 v{current}",
]
_ERROR_LINES = [
    "更新失败: \n  {error}",
]

# 配置字段（key -> label / type / hint / group / variables / default）
CONFIG_FIELDS = {
    "proxy": {
        "label": "GitHub 代理",
        "type": "text",
        "hint": "留空则不使用代理，默认 https://gh-proxy.com/",
        "default": "https://gh-proxy.com/",
    },
    "max_retries": {
        "label": "重试次数",
        "type": "int",
        "hint": "网络请求失败时的重试次数",
        "default": 3,
    },
    "schedule_enabled": {
        "label": "自动更新",
        "type": "bool",
        "hint": "按下面的时间自动更新",
        "default": True,
    },
    "schedule_cron": {
        "label": "自动更新表达式（cron）",
        "type": "text",
        "hint": "五段式，例如 0 4 * * * 表示每天 04:00",
        "default": "0 4 * * *",
    },
    "notify_session": {
        "label": "定时更新通知会话",
        "type": "text",
        "hint": "unified_msg_origin，例如 aiocqhttp:FriendMessage:123；留空则用最近一次 /query update 的会话，都没有则不发送",
        "default": "",
    },
    "message_checking": {
        "label": "检查中提示",
        "type": "template",
        "group": "messages",
        "hint": "变量 {current}",
        "default": "\n".join(_CHECKING_LINES),
        "variables": ["current"],
    },
    "message_found": {
        "label": "检测结果",
        "type": "template",
        "group": "messages",
        "hint": "变量 {current} {latest} {latest_sha7}",
        "default": "\n".join(_FOUND_LINES),
        "variables": ["current", "latest", "latest_sha", "latest_sha7"],
    },
    "message_done": {
        "label": "更新完成消息",
        "type": "template",
        "group": "messages",
        "hint": "变量 {current} {latest_sha7}",
        "default": "\n".join(_DONE_LINES),
        "variables": ["current", "latest_sha", "latest_sha7"],
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
    "latest_sha": "远端提交号",
    "latest_sha7": "远端短提交号",
    "error": "错误信息",
}

# 变量示例值，供模板预览使用
VAR_SAMPLES = {
    "current": "6.1.0",
    "latest": "6.1.1",
    "latest_sha": "2c54e39abcdef0123456789abcdef0123456789",
    "latest_sha7": "2c54e39",
    "error": "网络连接超时",
}