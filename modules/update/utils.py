# 插件更新模块配置：默认值与字段定义来自 config.yaml
#
# 脚本内不写默认值；要改默认代理或重试次数，改 config.yaml 即可。

from __future__ import annotations

from pathlib import Path

from ...common.module_config import load_defaults, load_fields

_CONFIG_FILE = Path(__file__).parent / "config.yaml"


def get_default_config() -> dict:
    return load_defaults(_CONFIG_FILE)


def get_config_fields() -> list[dict]:
    return load_fields(_CONFIG_FILE)
