# option.yml 的默认值
#
# 只依赖标准库：运行时的 option.py 与 Scripts/gen_option.py 共用这一份默认值，
# 避免脚本生成的默认文件与插件实际使用的不一致。

CHAPTER_RULE = "Bd/JP{Pindex:03}-{Pid}"

# 生成文件时的表头；option.py 与 Scripts/gen_option.py 共用
HEADER = """# JMComic 下载参数（jmcomic 原生 option 配置文件）
#
# 由插件按 Views「JM 下载 → 下载」表单生成并维护；表单保存会重写下面这些键，
# 手工添加的其它配置（plugins、client.domain 等）会保留。
# 默认值可用 Scripts/gen_option.py 重新生成。
"""

# 与 jmcomic 2.7.10 的默认值对齐，只写插件关心的项；
# client.postman.meta_data 不预置，交给库默认（系统代理）
DEFAULT_OPTION = {
    "log": False,
    "dir_rule": {
        "rule": CHAPTER_RULE,
        "base_dir": ".",
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