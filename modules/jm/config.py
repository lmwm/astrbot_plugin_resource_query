# JM 模块配置
#
# 字段顺序即 Views 的显示顺序；用户的改动保存在 plugin_data 的 config.json，
# 这里只提供默认值与界面定义。
# 消息模板用 {变量} 占位，每个模板可用的变量写在字段的 variables 里（Views 据此过滤标签）。

# 消息模板默认内容（按行拼接，便于阅读）
_INFO_LINES = [
    "I  D：{id}",
    "标题：{title}",
    "作者：{author}",
]
_START_LINES = [
    "JM{id} 开始下载…",
]
_CACHED_LINES = [
    "JM{id} 使用本地缓存…",
]
_PROGRESS_LINES = [
    "下载中 {percent}%",
]
_PROGRESS_COUNT_LINES = [
    "已下载 {done} 张",
]
_DONE_LINES = [
    "√ 下载完成",
]
_ERROR_LINES = [
    "× 下载失败：{error}",
]
_TOO_LARGE_LINES = [
    "! 文件 {size_mb} MB 超过上限 {max_size_mb} MB，未发送",
]
_SEND_FAILED_LINES = [
    "× 发送失败：{error}",
]
_NO_PDF_LINES = [
    "! 下载完成但未生成 PDF 文件",
]

# 配置字段（key -> label / type / hint / group / variables / default）
CONFIG_FIELDS = {
    #  下载
    "jm_image_threads": {
        "label": "图片并发数",
        "type": "int",
        "group": "download",
        "hint": "单章节内的图片下载并发",
        "default": 10,
    },
    "jm_photo_threads": {
        "label": "章节并发数",
        "type": "int",
        "group": "download",
        "hint": "章节之间的下载并发",
        "default": 2,
    },
    "jm_max_concurrent": {
        "label": "同时下载任务数",
        "type": "int",
        "group": "download",
        "hint": "限制同时进行的漫画下载数量",
        "default": 2,
    },
    "jm_timeout": {
        "label": "请求超时（秒）",
        "type": "int",
        "group": "download",
        "hint": "单次网络请求的超时时间",
        "default": 20,
    },
    "jm_retry_times": {
        "label": "重试次数",
        "type": "int",
        "group": "download",
        "hint": "网络请求失败后的重试次数",
        "default": 3,
    },
    "jm_proxy": {
        "label": "代理地址",
        "type": "text",
        "group": "download",
        "hint": "如 127.0.0.1:7890 或 http://127.0.0.1:7890，留空不使用代理",
        "default": "",
    },
    "jm_cookies": {
        "label": "Cookie",
        "type": "password",
        "group": "download",
        "hint": "格式 k=v; k2=v2，用于访问登录可见内容",
        "default": "",
    },
    "jm_jpeg_quality": {
        "label": "PDF 画质（JPEG 质量）",
        "type": "int",
        "group": "download",
        "hint": "取值 1-95，越大越清晰体积越大。原图为 webp，生成 PDF 时二次压缩为 JPEG；实测 26 页：50→5.7MB、75→7.7MB、90→11.3MB",
        "default": 75,
    },
    #  发送与文件
    "jm_send_file": {
        "label": "下载后发送 PDF",
        "type": "bool",
        "group": "output",
        "hint": "关闭后不发送文件，只回复下载完成提示",
        "default": False,
    },
    "jm_max_file_size": {
        "label": "文件大小上限（MB）",
        "type": "int",
        "group": "output",
        "hint": "超过则不发送，0 表示不限制",
        "default": 10,
    },
    "jm_show_info": {
        "label": "发送漫画信息",
        "type": "bool",
        "group": "output",
        "hint": "是否单独发送一条漫画详情（ID、标题、作者）；使用本地缓存时同样会发送",
        "default": False,
    },
    "jm_info_after_download": {
        "label": "详情在下载完成后发送",
        "type": "bool",
        "group": "output",
        "hint": "关闭则在发送「开始下载」之前先发送详情；开启则等下载完成后再发送详情",
        "default": False,
    },
    #  消息模板
    "message_info": {
        "label": "漫画信息",
        "type": "template",
        "group": "messages",
        "hint": "变量 {id} {title} {author} {pages} {chapters}",
        "default": "\n".join(_INFO_LINES),
        "variables": ["id", "title", "author", "pages", "chapters"],
    },
    "message_start": {
        "label": "开始下载",
        "type": "template",
        "group": "messages",
        "hint": "变量 {id} {title}",
        "default": "\n".join(_START_LINES),
        "variables": ["id", "title"],
    },
    "message_cached": {
        "label": "使用本地缓存",
        "type": "template",
        "group": "messages",
        "hint": "变量 {id} {title} {size_mb}",
        "default": "\n".join(_CACHED_LINES),
        "variables": ["id", "title", "size_mb"],
    },
    "message_progress": {
        "label": "下载进度",
        "type": "template",
        "group": "messages",
        "hint": "总页数已知时使用；变量 {percent} {done} {total}",
        "default": "\n".join(_PROGRESS_LINES),
        "variables": ["percent", "done", "total"],
    },
    "message_progress_count": {
        "label": "下载进度（总页数未知）",
        "type": "template",
        "group": "messages",
        "hint": "总页数未知时使用；变量 {done}",
        "default": "\n".join(_PROGRESS_COUNT_LINES),
        "variables": ["done"],
    },
    "message_done": {
        "label": "下载完成",
        "type": "template",
        "group": "messages",
        "hint": "不发送文件时回复这条；变量 {id} {title} {size_mb} {pages}",
        "default": "\n".join(_DONE_LINES),
        "variables": ["id", "title", "size_mb", "pages"],
    },
    "message_error": {
        "label": "失败消息",
        "type": "template",
        "group": "messages",
        "hint": "变量 {id} {title} {error}",
        "default": "\n".join(_ERROR_LINES),
        "variables": ["id", "title", "error"],
    },
    "message_too_large": {
        "label": "文件超过上限",
        "type": "template",
        "group": "messages",
        "hint": "变量 {id} {title} {size_mb} {max_size_mb}",
        "default": "\n".join(_TOO_LARGE_LINES),
        "variables": ["id", "title", "size_mb", "max_size_mb"],
    },
    "message_send_failed": {
        "label": "发送失败",
        "type": "template",
        "group": "messages",
        "hint": "变量 {id} {title} {error}",
        "default": "\n".join(_SEND_FAILED_LINES),
        "variables": ["id", "title", "error"],
    },
    "message_no_pdf": {
        "label": "未生成 PDF",
        "type": "template",
        "group": "messages",
        "hint": "变量 {id} {title}",
        "default": "\n".join(_NO_PDF_LINES),
        "variables": ["id", "title"],
    },
}

# 配置分组：每组在 Views 里单独一页
CONFIG_GROUPS = [
    {
        "key": "download",
        "label": "下载",
    },
    {
        "key": "output",
        "label": "发送与文件",
    },
    {
        "key": "messages",
        "label": "消息模板",
    },
]

# 消息模板变量（变量配置页与标签使用）
VARIABLES = {
    "id": "漫画 ID",
    "title": "标题",
    "author": "作者",
    "pages": "页数",
    "chapters": "章节数",
    "size_mb": "PDF 大小（MB）",
    "max_size_mb": "文件大小上限（MB）",
    "percent": "下载进度（%）",
    "done": "已下载张数",
    "total": "总张数",
    "error": "错误信息",
}

# 变量示例值，供模板预览使用
VAR_SAMPLES = {
    "id": "181251",
    "title": "示例漫画",
    "author": "示例作者",
    "pages": "26",
    "chapters": "3",
    "size_mb": "7.7",
    "max_size_mb": "10",
    "percent": "42",
    "done": "12",
    "total": "26",
    "error": "网络连接超时",
}
