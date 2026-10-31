# 模块配置来源：只读的 config.yaml
#
# 结构（2026-10-31 起）：每个配置项一个块，默认值写在 value 里，
# label / type / hint 供 Views 渲染。示例：
#
#   proxy:
#     label: GitHub 代理
#     type: text
#     hint: 留空使用默认代理
#     value: "https://gh-proxy.com/"
#
# 兼容旧结构（defaults + fields 两段），jm 等模块仍可继续使用。

from __future__ import annotations

from pathlib import Path

from .yaml_utils import load_yaml_config


def _is_legacy(config: dict) -> bool:
    # 旧结构：顶层有 defaults / fields
    return "defaults" in config or "fields" in config


def load_defaults(config_file: Path) -> dict:
    # 读取默认值；缺失时返回空字典
    config = load_yaml_config(Path(config_file))

    if _is_legacy(config):
        defaults = config.get("defaults")
        return dict(defaults) if isinstance(defaults, dict) else {}

    defaults: dict = {}
    for key, item in config.items():
        if isinstance(item, dict):
            if "value" in item:
                defaults[key] = item["value"]
        else:
            # 兼容纯键值写法
            defaults[key] = item

    return defaults


def load_fields(config_file: Path) -> list[dict]:
    # 读取 Views 字段定义，按文件顺序返回
    config = load_yaml_config(Path(config_file))

    if _is_legacy(config):
        raw = config.get("fields")
        if not isinstance(raw, dict):
            return []
        legacy_fields: list[dict] = []
        for key, meta in raw.items():
            item = {"key": key}
            if isinstance(meta, dict):
                item.update(meta)
            legacy_fields.append(item)
        return legacy_fields

    fields: list[dict] = []
    for key, item in config.items():
        if not isinstance(item, dict):
            continue
        if "type" not in item and "label" not in item:
            continue

        field = {"key": key}
        field.update({k: v for k, v in item.items() if k != "value"})
        if "value" in item:
            field["default"] = item["value"]
        fields.append(field)

    return fields
