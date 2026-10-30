# 模块配置存储：默认值打底 + 用户已保存值覆盖

from __future__ import annotations

from pathlib import Path

from ..common.utils import load_json_file, save_json_file

# 模块配置文件名
MODULE_CONFIG_FILE = "config.json"


class ConfigStore:
    # 某个模块的 config.json 读写

    def __init__(self, config_path: Path, file_name: str = MODULE_CONFIG_FILE) -> None:
        self._path = Path(config_path) / file_name

    def load(self, defaults: dict) -> dict:
        config = dict(defaults)
        saved = load_json_file(self._path)
        if saved:
            config.update(saved)
        return config

    def save(self, config: dict) -> bool:
        return save_json_file(self._path, config)
