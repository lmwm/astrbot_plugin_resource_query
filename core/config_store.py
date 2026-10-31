# 模块配置存储
#
# 默认配置：modules/<模块>/config.yaml（只读，随插件发布）
# 用户配置：plugin_data/<插件>/config/<模块>/config.yaml（Views 保存，优先）
#
# 用户配置按默认配置的键写块结构：每个键下只有 value，结构与默认配置一致。
# 旧格式（扁平键值或 config.json）在读取时自动兼容并迁移。

from __future__ import annotations

import logging
from pathlib import Path

from ..common.utils import load_json_file
from ..common.yaml_utils import parse_yaml, save_yaml_file

logger = logging.getLogger(__name__)

MODULE_CONFIG_FILE = "config.yaml"
LEGACY_CONFIG_FILE = "config.json"


class ConfigStore:
    # 某个模块的用户配置读写

    def __init__(self, config_path: Path) -> None:
        self._path = Path(config_path) / MODULE_CONFIG_FILE
        self._legacy_path = Path(config_path) / LEGACY_CONFIG_FILE

    def load(self, defaults: dict) -> dict:
        # 默认值打底，再用用户配置覆盖
        config = dict(defaults)
        saved = self._load_saved()
        if saved:
            config.update(saved)
        return config

    def save(self, config: dict) -> bool:
        # 按默认配置的键写块结构，只保存值
        payload = {key: {"value": value} for key, value in config.items()}
        return save_yaml_file(self._path, payload)

    def _load_saved(self) -> dict:
        if self._path.exists():
            try:
                data = parse_yaml(self._path.read_text(encoding="utf-8"))
            except OSError:
                return {}
            return self._unwrap(data)

        # 旧版 JSON 迁移：写入 YAML 成功后删除旧文件
        legacy = load_json_file(self._legacy_path)
        if not legacy:
            return {}

        if self.save(legacy):
            try:
                self._legacy_path.unlink()
            except OSError:
                pass
            logger.info(
                f"[config] 已将 {self._legacy_path.name} 迁移为 {self._path.name}"
            )

        return legacy

    @staticmethod
    def _unwrap(data: dict) -> dict:
        # 兼容两种写法：{key: {value: x}} 与 {key: x}
        result: dict = {}
        for key, value in data.items():
            if isinstance(value, dict) and "value" in value:
                result[key] = value["value"]
            else:
                result[key] = value
        return result
