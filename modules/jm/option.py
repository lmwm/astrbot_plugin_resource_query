# JMComic option 配置文件
#
# 模块不再用代码拼 JmOption 字典，而是把下载参数写进 jmcomic 原生的
# option.yml，再用 JmOption.from_file() 读取，未知参数交给库自己解释。
#
# 表单保存时只重写表单对应的键（log、dir_rule、download、client.retry_times/
# timeout/postman），手工添加的其它配置（plugins、client.impl、domain 等）保留。
# 默认文件在插件数据目录；模块配置里把「下载参数文件」指向别的路径后，
# 模块只读该文件、不再生成或覆盖。

from __future__ import annotations

from pathlib import Path

from ...common.module_log import module_logger

logger = module_logger("jm")

# 每章一个子目录：Pindex 排序、Pid 保证唯一
CHAPTER_RULE = "Bd/JP{Pindex:03}-{Pid}"

_HEADER = """# JMComic 下载参数（jmcomic 原生 option 配置文件）
#
# 由插件按「JM 下载 → 下载」表单生成；表单保存会重写下面这些键，
# 手工添加的其它配置（plugins、client.impl、domain 等）会保留。
# 想完全手工维护，可在模块配置里把「下载参数文件」指向另一个路径。
"""


def _read(path: Path) -> dict:
    # 读取现有配置；格式错误时返回空字典，由调用方重新生成
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        logger.warning(f"读取 option 配置失败，将重新生成：{e}")
        return {}

    return data if isinstance(data, dict) else {}


def _write(path: Path, payload: dict) -> None:
    # 写入带表头注释的 option.yml
    import yaml

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = _HEADER + yaml.safe_dump(
            payload, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        logger.warning(f"写入 option 配置文件失败：{e}")


def ensure_file(path: Path, payload: dict) -> None:
    # 文件不存在时写入一份完整配置；已存在不覆盖，保留手工修改
    if not path.is_file():
        _write(path, payload)


def sync_file(path: Path, payload: dict) -> None:
    # 表单保存时把表单对应的键合并进现有文件；未知键保留
    current = _read(path)
    _deep_merge(current, payload)

    # postman.meta_data 由表单整体决定：清空代理/Cookie 时不能残留旧值
    meta = payload.get("client", {}).get("postman", {}).get("meta_data")
    if isinstance(meta, dict):
        current.setdefault("client", {}).setdefault("postman", {})["meta_data"] = meta

    _write(path, current)


def _deep_merge(target: dict, source: dict) -> dict:
    # 深度合并：source 覆盖 target 的同名键，dict 递归
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def load_option(path: Path, image_dir: Path):
    # 读取 option 文件；每本漫画的图片目录在运行时替换，不写回文件
    import jmcomic

    option = jmcomic.JmOption.from_file(str(path))
    option.dir_rule.base_dir = str(image_dir)
    return option
