# JMComic option 配置文件
#
# 下载参数的本体是 config/jm/option.yml（与 config.json 同目录），由 Views 表单
# 可视化编辑：config.py 的 OPTION_FIELDS 把表单字段映射到 option 的键，保存时
# 只改这些键；其它键（plugins、client.domain 等）仍可在文件里手工维护。
#
# 默认值来自 option_default.py；Scripts/gen_option.py 用同一份默认值生成文件。

from __future__ import annotations

import copy
from pathlib import Path

from ...common.module_log import module_logger
from .option_default import DEFAULT_OPTION, HEADER

logger = module_logger("jm")

# 「键不存在」哨兵
_MISSING = object()


def default_payload(base_dir: str | Path) -> dict:
    # 完整默认配置；base_dir 换成实际的下载根目录
    payload = copy.deepcopy(DEFAULT_OPTION)
    payload["dir_rule"]["base_dir"] = str(base_dir)
    return payload


def write_file(path: Path, payload: dict) -> bool:
    # 写入带表头注释的 option.yml；返回是否成功
    import yaml

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = HEADER + yaml.safe_dump(
            payload, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
        path.write_text(text, encoding="utf-8")
        return True
    except OSError as e:
        logger.warning(f"写入 option 配置文件失败：{e}")
        return False
    except yaml.YAMLError as e:
        logger.warning(f"生成 option 配置内容失败：{e}")
        return False


def _read(path: Path) -> dict:
    # 读取现有配置；文件缺失或格式错误时返回空字典
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        if path.is_file():
            logger.warning(f"读取 option 配置失败：{e}")
        return {}

    return data if isinstance(data, dict) else {}


def ensure_file(path: Path, base_dir: str | Path) -> None:
    # 文件不存在时写入默认配置；已存在不覆盖（保留表单与手工修改）
    if not path.is_file():
        write_file(path, default_payload(base_dir))


def reset_file(path: Path, base_dir: str | Path) -> None:
    # 恢复默认配置（Views 的「恢复默认」会调用）
    write_file(path, default_payload(base_dir))


def read_values(path: Path, specs: dict[str, dict]) -> dict:
    # 按表单字段从 option 文件读值；文件缺失时返回空字典，由字段默认值兜底
    data = _read(path)
    result: dict = {}
    for alias, spec in specs.items():
        value = _get(data, str(spec["path"]))
        if value is _MISSING:
            continue
        result[alias] = _to_form(value, str(spec["kind"]))
    return result


def update_values(path: Path, specs: dict[str, dict], values: dict) -> None:
    # 把表单值写回 option 文件；代理/Cookie 清空时删除对应键（回到库默认）
    data = _read(path)
    if not data:
        raise FileNotFoundError(f"option 配置文件不存在：{path}")

    for alias, raw in values.items():
        spec = specs.get(alias)
        if not spec:
            continue

        value, drop = _from_form(raw, str(spec["kind"]))
        if drop:
            _pop(data, str(spec["path"]))
        else:
            _set(data, str(spec["path"]), value)

    write_file(path, data)


def load_option(path: Path, image_dir: Path):
    # 读取 option 文件；每本漫画的图片目录在运行时替换，不写回文件
    import jmcomic

    option = jmcomic.JmOption.from_file(str(path))
    option.dir_rule.base_dir = str(image_dir)
    return option


#  点号路径读写


def _get(data: dict, path: str):
    node = data
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return _MISSING
        node = node[key]
    return node


def _set(data: dict, path: str, value) -> None:
    keys = path.split(".")
    node = data
    for key in keys[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[keys[-1]] = value


def _pop(data: dict, path: str) -> None:
    keys = path.split(".")
    node = data
    for key in keys[:-1]:
        node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return
    node.pop(keys[-1], None)


#  表单值 ↔ option 值

def _to_form(value, kind: str):
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    if kind == "bool":
        return bool(value)

    if kind == "suffix":
        return "" if value in (None, "") else str(value)

    if kind == "proxy":
        if isinstance(value, dict):
            return str(value.get("http") or value.get("https") or "")
        return str(value or "")

    if kind == "cookie":
        if isinstance(value, dict):
            return "; ".join(f"{key}={val}" for key, val in value.items())
        return str(value or "")

    return "" if value is None else str(value)


def _from_form(raw, kind: str):
    # 返回（写入值, 是否删除键）；代理/Cookie 留空时删除键
    if kind == "int":
        try:
            return int(raw), False
        except (TypeError, ValueError):
            return 0, False

    if kind == "bool":
        return bool(raw), False

    if kind == "suffix":
        text = str(raw or "").strip()
        return (text, False) if text else (None, False)

    if kind == "proxy":
        text = str(raw or "").strip()
        if not text:
            return None, True
        proxy = text if "://" in text else f"http://{text}"
        return {"http": proxy, "https": proxy}, False

    if kind == "cookie":
        text = str(raw or "").strip()
        if not text:
            return None, True

        cookies: dict[str, str] = {}
        for part in text.replace("\n", ";").split(";"):
            key, separator, value = part.strip().partition("=")
            if separator and key.strip():
                cookies[key.strip()] = value.strip()
        return cookies, False

    return str(raw or ""), False