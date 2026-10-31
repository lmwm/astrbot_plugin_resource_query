# 模块配置存储
#
# 默认配置：modules/<模块>/config.yaml（只读，随插件发布）
# 用户配置：plugin_data/<插件>/config/<模块>/config.yaml（Views 保存，优先）
# 旧版本的 config.json 在首次读取时自动迁移为 config.yaml，成功后删除旧文件。

from __future__ import annotations

import logging
from pathlib import Path

from ..common.utils import load_json_file
from ..common.yaml_utils import parse_yaml, save_yaml_file

logger = logging.getLogger(__name__)

# 用户配置文件名与旧版文件名
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
        return save_yaml_file(self._path, config)

    def _load_saved(self) -> dict:
        if self._path.exists():
            try:
                data = parse_yaml(self._path.read_text(encoding="utf-8"))
            except OSError:
                return {}
            return data if isinstance(data, dict) else {}

        # 旧版 JSON 迁移：写入 YAML 成功后删除旧文件
        legacy = load_json_file(self._legacy_path)
        if not legacy:
            return {}

        if save_yaml_file(self._path, legacy):
            try:
                self._legacy_path.unlink()
            except OSError:
                pass
            logger.info(
                f"[config] 已将 {self._legacy_path.name} 迁移为 {self._path.name}"
            )

        return legacy
