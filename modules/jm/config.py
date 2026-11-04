# JM 模块配置
#
# 字段顺序即 Views 的显示顺序；用户的改动保存在 plugin_data 的 config.json，
# 这里只提供默认值与界面定义。
# 消息模板用 {变量} 占位，每个模板可用的变量写在字段的 variables 里（Views 据此过滤标签）。

import re

from .option_default import DIR_RULE as DEFAULT_DIR_RULE

# 插件名占位符：写入配置时用它代替实际插件名，改名后无需同步修改
PLUGIN_NAME_TOKEN = "{plugin}"

# 目录规则在表单里省略开头的 Bd/
DIR_RULE_BODY = DEFAULT_DIR_RULE[len("Bd/") :] if DEFAULT_DIR_RULE.startswith("Bd/") else ""

# 目录规则里允许的占位符（{title} 由模块解析，其余由 jmcomic 解析）
RULE_FIELDS = {
    "title",
    "Pid",
    "Pindex",
    "Pname",
    "Ptitle",
    "Psort",
    "Aid",
    "Aname",
    "Aoname",
    "Atitle",
    "Aauthor",
}

_RULE_TOKEN_RE = re.compile(r"\{([^{}]*)\}")

# 默认下载目录：相对 AstrBot 数据根，用占位符避免写死插件名
DEFAULT_DOWNLOAD_DIR = f"plugin_data/{PLUGIN_NAME_TOKEN}/JMDownload"

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
_MISSING_DEPS_LINES = [
    "× 缺少运行依赖：{deps}",
    "插件初始化时已尝试自动补装但未成功，请在 AstrBot 插件管理中重装插件；",
    "仍失败时可在 AstrBot 的 Python 环境里手动安装",
]

# 配置字段（key -> label / type / hint / group / variables / default）
CONFIG_FIELDS = {
    #  下载参数（这些字段写入 config/jm/option.yml，不再存进 config.json）
    "jm_download_dir": {
        "label": "下载路径",
        "type": "text",
        "group": "option",
        "hint": (
            "相对 AstrBot 数据根（data/）的目录，实际是 "
            "「data/plugin_data/<插件目录名>/JMDownload」；插件改名后自动跟随，无需修改。"
            "对应 option.yml 的 dir_rule.base_dir"
        ),
        # 保存时仍写 {plugin} 占位符，显示时替换成真实路径
        "default": DEFAULT_DOWNLOAD_DIR,
        "tokens": [
            {"label": "插件默认位置", "value": DEFAULT_DOWNLOAD_DIR},
            {"label": "JMDownload", "value": "JMDownload"},
            {"label": "jm/漫画", "value": "jm/漫画"},
        ],
    },
    "jm_dir_rule": {
        "label": "目录规则",
        "type": "rule",
        "group": "option",
        "hint": "决定图片放在哪个子目录；点击名称后的「可用参数」查看全部字段",
        # 表单只显示 Bd 之后的部分
        "default": DIR_RULE_BODY,
        "help": {
            "title": "目录规则可用参数",
            "intro": (
                "规则用 / 分隔层级，省略开头的 Bd/（下载根由「下载路径」决定）。"
                "方括号 {Xxx} 会被替换成对应字段；{Pindex:03} 表示补零到 3 位（P001）。"
                "留空或填 Bd 表示图片直接放 JM <ID> 根目录。"
            ),
            "groups": [
                {
                    "title": "本子（整本共用）",
                    "items": [
                        {"name": "Aid", "desc": "本子 ID，如 350234"},
                        {"name": "Atitle", "desc": "本子完整标题（含作者、社团等前缀）"},
                        {"name": "Aname", "desc": "本子名称，通常与 Atitle 相同"},
                        {"name": "Aoname", "desc": "本子原始短名，常更简洁"},
                        {"name": "Aauthor", "desc": "作者名"},
                        {"name": "Aauthoroname", "desc": "作者原始名"},
                    ],
                },
                {
                    "title": "章节（每个章节不同）",
                    "items": [
                        {"name": "Pindex", "desc": "章节序号，从 1 开始；{Pindex:03} 补零成 P001"},
                        {"name": "Pid", "desc": "章节 ID；单章节本子与本子 ID 相同"},
                        {"name": "Ptitle", "desc": "章节标题（首章常为空，建议改用 {title}）"},
                        {"name": "Pname", "desc": "章节名，通常同 Ptitle"},
                        {"name": "Psort", "desc": "站点给的排序号（不补零时用这个）"},
                    ],
                },
                {
                    "title": "模块扩展",
                    "items": [
                        {
                            "name": "title",
                            "desc": "模块解析的标题：优先中文短名，并按「目录繁简转换」统一简繁",
                        },
                    ],
                },
            ],
            "examples": [
                {
                    "rule": "JM{Aid}-P{Pindex:03}-{title}",
                    "result": "JM350234-P001-董卓 上+下/",
                    "note": "默认：每章一个目录",
                },
                {
                    "rule": "{Aauthor}/{title}/P{Pindex:03}",
                    "result": "KINN/董卓 上+下/P001/",
                    "note": "按作者、本子、章节三级分",
                },
                {
                    "rule": "{title}",
                    "result": "董卓 上+下/",
                    "note": "所有章节的图片放同一目录（同名会覆盖）",
                },
            ],
        },
        "tokens": [
            {"label": "本子ID-章节-标题", "value": "JM{Aid}-P{Pindex:03}-{title}"},
            {"label": "本子ID/章节", "value": "JM{Aid}/P{Pindex:03}"},
            {"label": "作者/标题", "value": "{Aauthor}/{title}"},
            {"label": "标题", "value": "{title}"},
        ],
    },
    "jm_download_log": {
        "label": "输出下载日志",
        "type": "bool",
        "group": "option",
        "hint": "开启 jmcomic 的下载日志（写入 AstrBot 日志，内容较多）；对应 option.yml 的 log",
        "default": True,
    },
    "jm_normalize_zh": {
        "label": "目录繁简转换",
        "type": "text",
        "group": "option",
        "hint": (
            "把目录名统一为 zh-cn（简体，默认）或 zh-tw（繁体）；留空不转换；"
            "依赖 zhconv；对应 option.yml 的 dir_rule.normalize_zh"
        ),
        "default": "zh-cn",
    },
    "jm_image_threads": {
        "label": "图片并发数",
        "type": "int",
        "group": "option",
        "hint": "单章节内的图片下载并发；对应 option.yml 的 download.threading.image",
        "default": 10,
    },
    "jm_photo_threads": {
        "label": "章节并发数",
        "type": "int",
        "group": "option",
        "hint": "章节之间的下载并发；对应 option.yml 的 download.threading.photo",
        "default": 2,
    },
    "jm_download_cache": {
        "label": "使用下载缓存",
        "type": "bool",
        "group": "option",
        "hint": "图片文件已存在时跳过重新下载；对应 option.yml 的 download.cache",
        "default": True,
    },
    "jm_image_decode": {
        "label": "还原混淆图",
        "type": "bool",
        "group": "option",
        "hint": "按站点规则还原被打乱的图片；对应 option.yml 的 download.image.decode",
        "default": True,
    },
    "jm_image_suffix": {
        "label": "图片后缀",
        "type": "text",
        "group": "option",
        "hint": (
            "留空按站点原格式保存（多为 webp，保留原图存档）；"
            "填 .jpg 则在下载时转成 JPEG（PDF 直嵌）；对应 option.yml 的 download.image.suffix"
        ),
        "default": "",
    },
    "jm_client_impl": {
        "label": "客户端类型",
        "type": "text",
        "group": "option",
        "hint": "api 为 APP 端（默认，限 IP 少），html 为网页端；对应 option.yml 的 client.impl",
        "default": "api",
    },
    "jm_retry_times": {
        "label": "重试次数",
        "type": "int",
        "group": "option",
        "hint": "网络请求失败后的重试次数；对应 option.yml 的 client.retry_times",
        "default": 3,
    },
    "jm_timeout": {
        "label": "请求超时（秒）",
        "type": "int",
        "group": "option",
        "hint": "单次网络请求的超时时间；对应 option.yml 的 client.timeout",
        "default": 20,
    },
    "jm_proxy": {
        "label": "代理地址",
        "type": "text",
        "group": "option",
        "hint": (
            "如 127.0.0.1:7890 或 http://127.0.0.1:7890；未写协议时自动补 http://，"
            "留空使用系统代理；对应 option.yml 的 client.postman.meta_data.proxies"
        ),
        "default": "",
    },
    "jm_cookies": {
        "label": "Cookie",
        "type": "password",
        "group": "option",
        "hint": (
            "格式 k=v; k2=v2（也可换行分隔），用于访问登录可见内容；"
            "对应 option.yml 的 client.postman.meta_data.cookies"
        ),
        "default": "",
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
    "message_missing_deps": {
        "label": "缺少运行依赖",
        "type": "template",
        "group": "messages",
        "hint": "变量 {deps}；依赖装在 AstrBot 的 site-packages，初始化补装失败时才发送",
        "default": "\n".join(_MISSING_DEPS_LINES),
        "variables": ["deps"],
    },
}

# 下载参数的字段映射：表单字段 → option.yml 的键
# 这些字段只存 option.yml，不写 config.json；kind 决定表单值与 option 值的转换
OPTION_FIELDS = {
    "jm_download_dir": {"path": "dir_rule.base_dir", "kind": "path"},
    "jm_dir_rule": {"path": "dir_rule.rule", "kind": "rule"},
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


def validate_dir_rule(rule: str) -> str | None:
    # 校验目录规则；返回错误文案，None 表示通过
    # 传入的是补回 Bd/ 之后的完整 DSL
    text = str(rule or "").strip()
    if not text:
        return "目录规则不能为空；留空请填 Bd 或直接删掉内容以外的字段"

    if not text.startswith("Bd"):
        return "目录规则必须以 Bd 开头（表单里通常省略，保存时会自动补上）"

    parts = [part.strip() for part in text.split("/")]
    if any(not part for part in parts):
        return "目录规则里有多余的 /（如 Bd// 或结尾的 /）"

    if len(parts) < 2:
        return None  # 只有 Bd：图片直接放漫画根目录，合法

    for part in parts[1:]:
        # 占位符里的 : 是补零语法（{Pindex:03}），先剔除再查非法字符
        plain = _RULE_TOKEN_RE.sub("", part)
        bad = set(plain) & set('\\:*?"<>|')
        if bad:
            return (
                f"目录层级「{part}」含 Windows 非法字符："
                + " ".join(sorted(bad))
            )

        for token in _RULE_TOKEN_RE.findall(part):
            name = token.split(":", 1)[0].strip()
            if name not in RULE_FIELDS:
                allowed = " ".join("{" + field + "}" for field in sorted(RULE_FIELDS))
                return f"未知占位符 {{{token}}}；可用：{allowed}"
            # 格式说明只允许数字补零写法（如 {Pindex:03}）
            if ":" in token:
                spec = token.split(":", 1)[1].strip()
                if not spec.isdigit():
                    return f"占位符 {{{token}}} 的格式只支持数字补零，如 {{Pindex:03}}"

    # 单个层级里不能出现盘符式冒号等已由上一步拦下，这里检查层级数量上限
    if len(parts) - 1 > 6:
        return "目录层级过多（最多 6 层），请精简规则"

    return None
