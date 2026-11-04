# JMComic option 配置文件
#
# 下载参数的本体是 config/jm/option.yml（与 config.json 同目录），由 Views 表单
# 可视化编辑：config.py 的 OPTION_FIELDS 把表单字段映射到 option 的键，保存时
# 只改这些键；其它键（plugins、client.domain 等）仍可在文件里手工维护。
#
# 默认值来自 option_default.py；Scripts/gen_option.py 用同一份默认值生成文件。

from __future__ import annotations

import copy
import logging
from pathlib import Path

from ...common.module_log import module_logger
from .option_default import (
    DEFAULT_OPTION,
    DIR_RULE,
    HEADER,
    LEGACY_CHAPTER_RULE,
)

logger = module_logger("jm")

# 「键不存在」哨兵
_MISSING = object()


class _JmLogBridge(logging.Handler):
    # 把 jmcomic 的记录转给插件 logger，确保进入 AstrBot 日志
    # 库自带的 handler 与 root 传播在不同运行环境下不一定被收集，桥接最稳

    def __init__(self) -> None:
        super().__init__(logging.INFO)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            logger.info(f"[jmcomic] {record.getMessage()}")
        except Exception:  # noqa: BLE001
            self.handleError(record)


def _ensure_log_bridge() -> None:
    # 同一个 logger 只挂一个桥接 handler，插件重载后仍复用
    jm_logger = logging.getLogger("jmcomic")
    if any(getattr(handler, "_astrbot_jm_bridge", False) for handler in jm_logger.handlers):
        return

    bridge = _JmLogBridge()
    bridge._astrbot_jm_bridge = True
    jm_logger.addHandler(bridge)


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


def read_rule(path: Path) -> str:
    # 当前目录规则；缺省按库根规则 Bd 处理
    data = _read(path)
    rule = data.get("dir_rule", {}).get("rule") if isinstance(data.get("dir_rule"), dict) else None
    return str(rule or DIR_RULE).strip()


def migrate_legacy_rule(path: Path) -> bool:
    # 6.14–6.19 用过的章节子目录规则改回 Bd（图片直接放图片目录）
    data = _read(path)
    if not data or not isinstance(data.get("dir_rule"), dict):
        return False

    rule = str(data["dir_rule"].get("rule") or "").strip()
    if rule != LEGACY_CHAPTER_RULE:
        return False

    data["dir_rule"]["rule"] = DIR_RULE
    write_file(path, data)
    return True


def _dir_rule_instance(jmcomic, rule: str, image_dir: Path, normalize_zh):
    # 用运行时规则重建 DirRule（base_dir 固定为漫画根）
    return jmcomic.DirRule(
        rule=rule,
        base_dir=str(image_dir),
        normalize_zh=normalize_zh,
    )


def load_option(path: Path, image_dir: Path, rule: str | None = None):
    # 读取 option 文件；每本漫画的目录在运行时替换，不写回文件
    import jmcomic

    data = _read(path)
    option = jmcomic.JmOption.from_file(str(path))
    option.dir_rule.base_dir = str(image_dir)

    # 单章节：JM<ID>-<标题>/；多章节：JM<ID>-<序号:03>-<标题>/
    if rule:
        option.dir_rule = _dir_rule_instance(
            jmcomic, rule, image_dir, option.dir_rule.normalize_zh
        )

    # 库只有 disable_jm_log，没有对应的 enable；log 在运行中改成 true 后
    # 需要显式恢复开关，否则会被之前加载的 log: false 永久关掉
    if data.get("log"):
        jmcomic.JmModuleConfig.FLAG_ENABLE_JM_LOG = True

        # 确保日志能进 AstrBot：库自己的 StreamHandler 不一定被收集，
        # 这里恢复传播与 INFO 级别（download_progress 插件会关掉传播）
        jm_logger = logging.getLogger("jmcomic")
        jm_logger.setLevel(logging.INFO)
        jm_logger.disabled = False
        if not jm_logger.propagate:
            jm_logger.propagate = True
        _ensure_log_bridge()

        root = logging.getLogger()
        logger.info(
            f"jmcomic 下载日志已开启（FLAG={jmcomic.JmModuleConfig.FLAG_ENABLE_JM_LOG}，"
            f"propagate={jm_logger.propagate}，level={jm_logger.level}，"
            f"handlers={[type(item).__name__ for item in jm_logger.handlers]}，"
            f"root_handlers={[type(item).__name__ for item in root.handlers]}）"
        )
    else:
        logger.info("jmcomic 下载日志已关闭")

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

    if kind == "path":
        text = str(value or "").strip()
        return text.replace("\\", "/")

    if kind == "suffix":
        return "" if value in (None, "") else str(value)

    if kind == "zh":
        return "" if value is None else str(value)

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

    if kind == "path":
        text = str(raw or "").strip().replace("\\", "/")
        return text or DEFAULT_OPTION["dir_rule"]["base_dir"], False

    if kind == "suffix":
        text = str(raw or "").strip()
        return (text, False) if text else (None, False)

    if kind == "zh":
        text = str(raw or "").strip().lower()
        return (text if text in ("zh-cn", "zh-tw") else None), False

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