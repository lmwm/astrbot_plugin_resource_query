# 模块配置来源：只读的 config.yaml
#
# 模块的默认值与 Views 字段定义统一放在 modules/<模块>/config.yaml，
# 脚本内不再写死；用户保存的值存 config/<模块>/config.json，优先级更高。
# 合并逻辑在 core/config_store.py：先取 YAML 默认值，再用 JSON 覆盖。

from __future__ import annotations

from pathlib import Path

from .yaml_utils import get_config_value, load_yaml_config


def load_defaults(config_file: Path) -> dict:
    # 读取 config.yaml 的 defaults 段；缺失时返回空字典
    defaults = get_config_value(load_yaml_config(Path(config_file)), "defaults", None)
    return dict(defaults) if isinstance(defaults, dict) else {}


def load_fields(config_file: Path) -> list[dict]:
    # 读取 config.yaml 的 fields 段，按声明顺序转为 Views 字段列表
    raw = get_config_value(load_yaml_config(Path(config_file)), "fields", None)
    if not isinstance(raw, dict):
        return []

    fields: list[dict] = []
    for key, meta in raw.items():
        item = {"key": key}
        if isinstance(meta, dict):
            item.update(meta)
        fields.append(item)

    return fields
