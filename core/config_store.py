# 模块配置存储
#
# 默认配置：modules/<模块>/config.yaml（随插件发布，只作为初始模板）
# 用户配置：plugin_data/<插件>/config/<模块>/config.yaml（唯一来源）
#
# 首次加载把默认配置复制到用户目录，之后只看用户配置；
# 用户配置包含字段定义（label/type/hint）、值（value）与可选的 variables 段。
# 旧版本配置（只有值、缺字段定义）会在读取时补全；旧 config.json / var_config.json 自动迁移。

from __future__ import annotations

import logging
from pathlib import Path

from ..common.utils import load_json_file
from ..common.yaml_utils import parse_yaml, save_yaml_file

logger = logging.getLogger(__name__)

MODULE_CONFIG_FILE = "config.yaml"
LEGACY_CONFIG_FILE = "config.json"
LEGACY_VAR_FILE = "var_config.json"

# 用户配置中的变量段（与字段块并列）
VARIABLES_KEY = "variables"


class ConfigStore:
    # 某个模块的用户配置读写

    def __init__(self, config_path: Path, default_path: Path | None = None) -> None:
        self._dir = Path(config_path)
        self._path = self._dir / MODULE_CONFIG_FILE
        self._legacy_path = self._dir / LEGACY_CONFIG_FILE
        self._legacy_var_path = self._dir / LEGACY_VAR_FILE
        self._default_path = Path(default_path) if default_path else None
        self._prepared = False

    #  准备（复制 / 迁移）

    def _default_data(self) -> dict:
        if self._default_path is None or not self._default_path.exists():
            return {}
        try:
            data = parse_yaml(self._default_path.read_text(encoding="utf-8"))
        except OSError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _has_fields(data: dict) -> bool:
        # 默认配置是否包含可渲染的字段定义
        return any(
            isinstance(value, dict) and ("type" in value or "label" in value)
            for key, value in data.items()
            if key != VARIABLES_KEY
        )

    def _prepare(self) -> None:
        if self._prepared:
            return
        self._prepared = True

        if self._path.exists():
            self._migrate_existing()
            return

        legacy = load_json_file(self._legacy_path)
        if legacy:
            data = self._merge_defaults(legacy)
            self._write(data)
            self._unlink(self._legacy_path)
            logger.info(
                f"[config] 已将 {self._legacy_path.name} 迁移为 {self._path.name}"
            )
            return

        default_data = self._default_data()
        if self._has_fields(default_data):
            self._write(default_data)

    def _migrate_existing(self) -> None:
        # 补全旧版本缺失的字段定义（保留用户已保存的值）
        data = self._read_raw()
        default_data = self._default_data()
        if not default_data:
            return

        changed = False
        for key, item in default_data.items():
            if key == VARIABLES_KEY or not isinstance(item, dict):
                continue
            current = data.get(key)
            if not isinstance(current, dict):
                data[key] = dict(item)
                changed = True
                continue
            for meta_key, meta_value in item.items():
                if meta_key != "value" and meta_key not in current:
                    current[meta_key] = meta_value
                    changed = True

        if changed:
            self._write(data)

    def _merge_defaults(self, saved: dict) -> dict:
        # 旧 JSON（扁平值）与默认字段定义合并
        data = self._default_data()
        for key, value in saved.items():
            if key == VARIABLES_KEY:
                data[key] = value
                continue
            current = data.get(key)
            if isinstance(current, dict):
                current["value"] = value
            else:
                data[key] = {"value": value}
        return data

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

    #  读取

    def _read_raw(self) -> dict:
        try:
            data = parse_yaml(self._path.read_text(encoding="utf-8"))
        except OSError:
            return {}
        return data if isinstance(data, dict) else {}

    def _read(self) -> dict:
        self._prepare()
        return self._read_raw()

    def fields(self) -> list[dict]:
        # 字段定义（label/type/hint/default），按用户配置顺序
        fields: list[dict] = []
        for key, item in self._read().items():
            if key == VARIABLES_KEY or not isinstance(item, dict):
                continue
            if "type" not in item and "label" not in item:
                continue
            field = {"key": key}
            field.update({k: v for k, v in item.items() if k != "value"})
            if "value" in item:
                field["default"] = item["value"]
            fields.append(field)
        return fields

    def values(self) -> dict:
        # 字段值
        values: dict = {}
        for key, item in self._read().items():
            if key == VARIABLES_KEY:
                continue
            if isinstance(item, dict):
                if "value" in item:
                    values[key] = item["value"]
            else:
                values[key] = item
        return values

    def variables(self) -> dict:
        # 变量配置（name -> {desc, default, show}）；兼容旧 var_config.json
        data = self._read()
        variables = data.get(VARIABLES_KEY)
        if isinstance(variables, dict):
            return variables

        legacy = load_json_file(self._legacy_var_path)
        if not legacy:
            return {}

        migrated: dict = {}
        for entry in legacy.get("variables") or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            migrated[str(entry["name"])] = {
                "desc": str(entry.get("desc") or ""),
                "default": str(entry.get("default") or ""),
                "show": bool(entry.get("show", True)),
            }

        if migrated:
            data[VARIABLES_KEY] = migrated
            self._write(data)
            self._unlink(self._legacy_var_path)

        return migrated

    #  写入

    def _write(self, data: dict) -> bool:
        return save_yaml_file(self._path, data)

    def save_values(self, values: dict) -> bool:
        data = self._read()
        for key, value in values.items():
            item = data.get(key)
            if isinstance(item, dict):
                item["value"] = value
            else:
                data[key] = {"value": value}
        return self._write(data)

    def save_variables(self, variables: dict) -> bool:
        data = self._read()
        data[VARIABLES_KEY] = variables
        return self._write(data)

    def reset(self) -> dict:
        # 用默认配置覆盖用户配置，返回默认值
        data = self._default_data()
        if not self._has_fields(data):
            return {}
        self._write(data)
        return {
            key: item["value"]
            for key, item in data.items()
            if key != VARIABLES_KEY and isinstance(item, dict) and "value" in item
        }
