# JM 模块配置
#
# 字段顺序即 Views 的显示顺序；用户的改动保存在 plugin_data 的 config.json，
# 这里只提供默认值与界面定义。
# 消息模板用 {变量} 占位，每个模板可用的变量写在字段的 variables 里（Views 据此过滤标签）。

from .option_default import DEFAULT_OPTION

# 插件名占位符：只在拼「相对数据根」的目录文案时使用；落盘前必须展开，
# 否则会生成字面量 {plugin} 目录
PLUGIN_NAME_TOKEN = "{plugin}"

# 下载目录模板（相对 AstrBot 数据根）：由 JMModule 展开成
# plugin_data/<插件目录名>/JMDownload，禁止直接当路径使用
DEFAULT_DOWNLOAD_DIR_TEMPLATE = f"plugin_data/{PLUGIN_NAME_TOKEN}/JMDownload"


def _option_default(*keys: str):
    # 表单默认值直接取 option.yml 的默认值，避免同一数字在 config.py 再写一遍
    node = DEFAULT_OPTION
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return ""
        node = node[key]
    return "" if node is None else node


# 多行模板默认内容（单行模板直接写在字段里）
_INFO_LINES = [
    "I  D：{id}",
    "标题：{title}",
    "作者：{author}",
]
_MISSING_DEPS_LINES = [
    "× 缺少运行依赖：{deps}",
    "插件初始化时已尝试自动补装但未成功，请在 AstrBot 插件管理中重装插件；",
    "仍失败时可在 AstrBot 的 Python 环境里手动安装",
]

# 配置字段（key -> label / type / hint / group / variables / default）
CONFIG_FIELDS = {
    #  下载参数（这些字段写入 config/jm/option.yml，不再存进 config.json）
    #  下载路径与目录规则不开放配置：固定为「数据根/plugin_data/<插件>/JMDownload」
    #  与「JM{Aid}-P{Pindex:03}-{title}」，避免用户改坏后找不到旧文件
    "jm_download_log": {
        "label": "输出下载日志",
        "type": "bool",
        "group": "option",
        "hint": "开启 jmcomic 的下载日志（写入 AstrBot 日志，内容较多）；对应 option.yml 的 log",
        "default": _option_default("log"),
    },
    "jm_normalize_zh": {
        "label": "目录繁简转换",
        "type": "text",
        "group": "option",
        "hint": (
            "把目录名统一为 zh-cn（简体，默认）或 zh-tw（繁体）；留空不转换；"
            "依赖 zhconv；对应 option.yml 的 dir_rule.normalize_zh"
        ),
        "default": _option_default("dir_rule", "normalize_zh"),
    },
    "jm_image_threads": {
        "label": "图片并发数",
        "type": "int",
        "group": "option",
        "hint": "单章节内的图片下载并发；对应 option.yml 的 download.threading.image",
        "default": _option_default("download", "threading", "image"),
    },
    "jm_photo_threads": {
        "label": "章节并发数",
        "type": "int",
        "group": "option",
        "hint": "章节之间的下载并发；对应 option.yml 的 download.threading.photo",
        "default": _option_default("download", "threading", "photo"),
    },
    "jm_download_cache": {
        "label": "使用下载缓存",
        "type": "bool",
        "group": "option",
        "hint": "图片文件已存在时跳过重新下载；对应 option.yml 的 download.cache",
        "default": _option_default("download", "cache"),
    },
    "jm_image_decode": {
        "label": "还原混淆图",
        "type": "bool",
        "group": "option",
        "hint": "按站点规则还原被打乱的图片；对应 option.yml 的 download.image.decode",
        "default": _option_default("download", "image", "decode"),
    },
    "jm_image_suffix": {
        "label": "图片后缀",
        "type": "text",
        "group": "option",
        "hint": (
            "留空按站点原格式保存（多为 webp，保留原图存档）；"
            "填 .jpg 则在下载时转成 JPEG（PDF 直嵌）；对应 option.yml 的 download.image.suffix"
        ),
        "default": _option_default("download", "image", "suffix"),
    },
    "jm_client_impl": {
        "label": "客户端类型",
        "type": "text",
        "group": "option",
        "hint": "api 为 APP 端（默认，限 IP 少），html 为网页端；对应 option.yml 的 client.impl",
        "default": _option_default("client", "impl"),
    },
    "jm_retry_times": {
        "label": "重试次数",
        "type": "int",
        "group": "option",
        "hint": "网络请求失败后的重试次数；对应 option.yml 的 client.retry_times",
        "default": _option_default("client", "retry_times"),
    },
    "jm_timeout": {
        "label": "请求超时（秒）",
        "type": "int",
        "group": "option",
        "hint": "单次网络请求的超时时间；对应 option.yml 的 client.timeout",
        "default": _option_default("client", "timeout"),
    },
    "jm_proxy": {
        "label": "代理地址",
        "type": "text",
        "group": "option",
        "hint": (
            "如 127.0.0.1:7890 或 http://127.0.0.1:7890；未写协议时自动补 http://，"
            "留空使用系统代理；对应 option.yml 的 client.postman.meta_data.proxies"
        ),
        "default": _option_default("client", "postman", "meta_data", "proxies"),
    },
    "jm_cookies": {
        "label": "Cookie",
        "type": "password",
        "group": "option",
        "hint": (
            "格式 k=v; k2=v2（也可换行分隔），用于访问登录可见内容；"
            "对应 option.yml 的 client.postman.meta_data.cookies"
        ),
        "default": _option_default("client", "postman", "meta_data", "cookies"),
    },
    "jm_max_concurrent": {
        "label": "同时下载任务数",
        "type": "int",
        "group": "output",
        "hint": "插件同时运行的漫画下载数，属于插件调度，不写入 option.yml",
        "default": 2,
    },
    "jm_jpeg_quality": {
        "label": "PDF 画质（JPEG 质量）",
        "type": "int",
        "group": "output",
        "hint": (
            "取值 1-95，越大越清晰体积越大。站点原图（多为 webp）会原样保留在图片目录作为存档；"
            "生成 PDF 时默认 75：JPEG 原图直接嵌入、webp 转 JPEG；其它值统一按目标质量转码。"
            "实测某 26 页 webp 本子：50→7.4MB、75→10.4MB、90→15.4MB（不同本子差异较大）"
        ),
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
        "hint": "单独发送的漫画详情；使用本地缓存时同样会发送",
        "default": "\n".join(_INFO_LINES),
        "variables": ["id", "title", "author", "pages", "chapters"],
    },
    "message_start": {
        "label": "开始下载",
        "type": "template",
        "group": "messages",
        "hint": "开始下载时发送",
        "default": "JM{id} 开始下载…",
        "variables": ["id", "title"],
    },
    "message_cached": {
        "label": "使用本地缓存",
        "type": "template",
        "group": "messages",
        "hint": "命中本地缓存、不重新下载时",
        "default": "JM{id} 使用本地缓存…",
        "variables": ["id", "title", "size_mb"],
    },
    "message_progress": {
        "label": "下载进度",
        "type": "template",
        "group": "messages",
        "hint": "总页数已知时使用（百分比）",
        "default": "下载中 {percent}%",
        "variables": ["percent", "done", "total"],
    },
    "message_progress_count": {
        "label": "下载进度（总页数未知）",
        "type": "template",
        "group": "messages",
        "hint": "总页数未知时使用（只报已下载张数）",
        "default": "已下载 {done} 张",
        "variables": ["done"],
    },
    "message_done": {
        "label": "下载完成",
        "type": "template",
        "group": "messages",
        "hint": "不发送文件时回复这条",
        "default": "√ 下载完成",
        "variables": ["id", "title", "size_mb", "pages"],
    },
    "message_error": {
        "label": "失败消息",
        "type": "template",
        "group": "messages",
        "hint": "下载失败时",
        "default": "× 下载失败：{error}",
        "variables": ["id", "title", "error"],
    },
    "message_too_large": {
        "label": "文件超过上限",
        "type": "template",
        "group": "messages",
        "hint": "文件超过大小上限、未发送时",
        "default": "! 文件 {size_mb} MB 超过上限 {max_size_mb} MB，未发送",
        "variables": ["id", "title", "size_mb", "max_size_mb"],
    },
    "message_send_failed": {
        "label": "发送失败",
        "type": "template",
        "group": "messages",
        "hint": "发送文件失败时",
        "default": "× 发送失败：{error}",
        "variables": ["id", "title", "error"],
    },
    "message_no_pdf": {
        "label": "未生成 PDF",
        "type": "template",
        "group": "messages",
        "hint": "下载完成但没有生成 PDF 时",
        "default": "! 下载完成但未生成 PDF 文件",
        "variables": ["id", "title"],
    },
    "message_missing_deps": {
        "label": "缺少运行依赖",
        "type": "template",
        "group": "messages",
        "hint": "依赖补装失败时；依赖装在 AstrBot 的 site-packages",
        "default": "\n".join(_MISSING_DEPS_LINES),
        "variables": ["deps"],
    },
}

# 下载参数的字段映射：表单字段 → option.yml 的键
# 这些字段只存 option.yml，不写 config.json；kind 决定表单值与 option 值的转换
OPTION_FIELDS = {
    "jm_download_log": {"path": "log", "kind": "bool"},
    "jm_normalize_zh": {"path": "dir_rule.normalize_zh", "kind": "zh"},
    "jm_image_threads": {"path": "download.threading.image", "kind": "int"},
    "jm_photo_threads": {"path": "download.threading.photo", "kind": "int"},
    "jm_download_cache": {"path": "download.cache", "kind": "bool"},
    "jm_image_decode": {"path": "download.image.decode", "kind": "bool"},
    "jm_image_suffix": {"path": "download.image.suffix", "kind": "suffix"},
    "jm_client_impl": {"path": "client.impl", "kind": "text"},
    "jm_retry_times": {"path": "client.retry_times", "kind": "int"},
    "jm_timeout": {"path": "client.timeout", "kind": "int"},
    "jm_proxy": {"path": "client.postman.meta_data.proxies", "kind": "proxy"},
    "jm_cookies": {"path": "client.postman.meta_data.cookies", "kind": "cookie"},
}

# 配置分组：每组在 Views 里单独一页
CONFIG_GROUPS = [
    {
        "key": "option",
        "label": "下载参数",
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
    "deps": "缺失的依赖",
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
    "deps": "jmcomic、Pillow",
}
