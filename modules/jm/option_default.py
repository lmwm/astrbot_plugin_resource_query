# option.yml 的默认值
#
# 只依赖标准库：运行时的 option.py 与 Scripts/gen_option.py 共用这一份默认值，
# 避免脚本生成的默认文件与插件实际使用的不一致。

# 默认且固定的目录规则：每本一个 JM<ID> 根，图片按章节分子目录
# {title} 由模块解析（优先含中文的 oname，并做繁简转换）；也可直接用库字段：
#   章节 Pid/Pindex/Pname/Ptitle/Psort，本子 Aid/Aname/Aoname/Atitle/Aauthor
# 注意：多章节本子的首章 Ptitle 常为空，用 {title} 比 {Ptitle} 稳
DIR_RULE = "Bd/JM{Aid}-P{Pindex:03}-{title}"

# 旧版章节子目录（6.14–6.19 的 Bd/JP{Pindex:03}-{Pid}）由 paths.cleanup_legacy_layout
# 在重新下载成功后清理，不在这里保留常量

# 生成文件时的表头；option.py 与 Scripts/gen_option.py 共用
HEADER = """# JMComic 下载参数（jmcomic 原生 option 配置文件）
#
# 由插件按 Views「JM 下载 → 下载参数」表单生成并维护；表单保存会重写下面这些键，
# 手工添加的其它配置（plugins 等）会保留。
# 默认值可用 Scripts/gen_option.py 重新生成。
"""

# 与 jmcomic 2.7.10 的默认值对齐，只写插件关心的项；
# client.postman.meta_data 不预置，交给库默认（系统代理）
DEFAULT_OPTION = {
    "log": True,
    "dir_rule": {
        "rule": DIR_RULE,
        "base_dir": "JMDownload",
        "normalize_zh": "zh-cn",
    },
    "download": {
        "cache": True,
        "image": {
            "decode": True,
            "suffix": None,
        },
        "threading": {
            "image": 10,
            "photo": 2,
        },
    },
    "client": {
        "impl": "api",
        "retry_times": 3,
        "timeout": 20,
    },
}