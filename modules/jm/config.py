# JM 模块配置
#
# 字段顺序即 Views 的显示顺序；用户的改动保存在 plugin_data 的 config.json，
# 这里只提供默认值与界面定义。

# 配置字段（key -> label / type / hint / default）
CONFIG_FIELDS = {
    "jm_send_file": {
        "label": "下载后发送 PDF",
        "type": "bool",
        "hint": "关闭后不发送文件",
        "default": True,
    },
    "jm_show_info": {
        "label": "发送漫画信息",
        "type": "bool",
        "hint": "是否单独发送一条漫画详情（ID、标题、作者、页数、简介）；使用本地缓存时同样会发送",
        "default": False,
    },
    "jm_info_after_download": {
        "label": "详情在下载完成后发送",
        "type": "bool",
        "hint": "关闭则在发送「开始下载」之前先发送详情；开启则等下载完成后再发送详情",
        "default": False,
    },
    "jm_max_file_size": {
        "label": "文件大小上限（MB）",
        "type": "int",
        "hint": "超过则不发送，0 表示不限制",
        "default": 10,
    },
    "jm_jpeg_quality": {
        "label": "PDF 画质（JPEG 质量）",
        "type": "int",
        "hint": "取值 1-95，越大越清晰体积越大。原图为 webp，生成 PDF 时二次压缩为 JPEG；实测 26 页：50→5.7MB、75→7.7MB、90→11.3MB",
        "default": 75,
    },
    "jm_max_concurrent": {
        "label": "同时下载任务数",
        "type": "int",
        "hint": "限制并发下载的漫画数量",
        "default": 2,
    },
    "jm_image_threads": {
        "label": "图片并发数",
        "type": "int",
        "hint": "单章节内的图片下载并发",
        "default": 10,
    },
    "jm_photo_threads": {
        "label": "章节并发数",
        "type": "int",
        "hint": "章节之间的下载并发",
        "default": 2,
    },
    "jm_timeout": {
        "label": "请求超时（秒）",
        "type": "int",
        "hint": "",
        "default": 20,
    },
    "jm_retry_times": {
        "label": "重试次数",
        "type": "int",
        "hint": "",
        "default": 3,
    },
    "jm_proxy": {
        "label": "代理地址",
        "type": "text",
        "hint": "如 127.0.0.1:7890 或 http://127.0.0.1:7890，留空不使用代理",
        "default": "",
    },
    "jm_cookies": {
        "label": "Cookie",
        "type": "password",
        "hint": "格式 k=v; k2=v2，用于访问登录可见内容",
        "default": "",
    },
}