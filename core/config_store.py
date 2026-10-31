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
        # 用户配置存在时只读它；不存在时把默认配置复制过来
        if self._path.exists():
            saved = self._load_saved()
            return saved if saved else dict(defaults)

        # 旧版 JSON 迁移：补全默认值后写入 YAML，成功再删旧文件
        legacy = load_json_file(self._legacy_path)
        if legacy:
            merged = {**defaults, **legacy}
            if self.save(merged):
                try:
                    self._legacy_path.unlink()
                except OSError:
                    pass
                logger.info(
                    f"[config] 已将 {self._legacy_path.name} 迁移为 {self._path.name}"
                )
            return merged

        # 没有默认值时不创建空配置（例如只读账号的模块）
        if defaults:
            self.save(defaults)
        return dict(defaults)

    def save(self, config: dict) -> bool:
        # 按默认配置的键写块结构，只保存值
        payload = {key: {"value": value} for key, value in config.items()}
        return save_yaml_file(self._path, payload)

    def _load_saved(self) -> dict:
        try:
            data = parse_yaml(self._path.read_text(encoding="utf-8"))
        except OSError:
            return {}
        return self._unwrap(data) if isinstance(data, dict) else {}

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
