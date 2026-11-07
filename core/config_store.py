# 模块配置存储
#
# 默认配置：各模块的 config.py（随插件发布，只读）
# 用户配置：plugin_data/<插件>/config/<模块>/config.json（只存值）
#
# 加载：用户 JSON 中的值优先，缺少的项回退默认值；没有文件时全部用默认值。
# 保存：写入本次提交的已知字段，未知键（如只读的 current_version）会被丢弃。
# 恢复默认：移除值键，variables 段保留。
# 迁移：旧 config.yaml / var_config.json 首次读取时转成 config.json 并删除。

from __future__ import annotations

import copy
from pathlib import Path

from ..common.module_log import module_logger
from ..common.utils import load_json_file, save_json_file

logger = module_logger("core")

CONFIG_FILE = "config.json"
LEGACY_YAML_FILE = "config.yaml"
LEGACY_VAR_FILE = "var_config.json"

# 用户配置中的变量段（与配置字段键并列）
VARIABLES_KEY = "variables"


class ConfigStore:
    # 某个模块的用户配置读写

    def __init__(
        self,
        config_path: Path,
        fields: dict[str, dict],
        variables: dict[str, str] | None = None,
    ) -> None:
        self._dir = Path(config_path)
        self._path = self._dir / CONFIG_FILE
        self._legacy_yaml_path = self._dir / LEGACY_YAML_FILE
        self._legacy_var_path = self._dir / LEGACY_VAR_FILE
        self._fields = fields or {}
        self._variable_defaults = variables or {}
        self._prepared = False

    #  默认值

    def default_values(self) -> dict:
        # 字段默认值（深拷贝，避免调用方改动影响后续读取）
        return {
            key: copy.deepcopy(meta.get("default")) for key, meta in self._fields.items()
        }

    #  迁移

    def _prepare(self) -> None:
        if self._prepared:
            return
        self._prepared = True

        data = self._read_raw()
        changed = False

        if self._path.exists():
            # JSON 已是唯一来源，清掉遗留的旧 YAML
            self._unlink(self._legacy_yaml_path)
        elif self._legacy_yaml_path.exists():
            legacy = self._load_legacy_yaml()
            if legacy:
                data.update(self._extract_values(legacy))
                migrated = self._extract_variables(legacy.get(VARIABLES_KEY))
                if migrated:
                    data[VARIABLES_KEY] = migrated
                changed = bool(data)
            self._unlink(self._legacy_yaml_path)
            if changed:
                logger.info(
                    f"[config] 已将 {self._legacy_yaml_path.name} 迁移为 {CONFIG_FILE}"
                )

        # 旧的变量文件（与配置分开存放）并入 variables 段
        legacy_vars = self._extract_variables(self._read_legacy_var_file())
        if legacy_vars:
            current = data.get(VARIABLES_KEY)
            current = current if isinstance(current, dict) else {}
            for name, item in legacy_vars.items():
                current.setdefault(name, item)
            data[VARIABLES_KEY] = current
            changed = True
            self._unlink(self._legacy_var_path)
            logger.info(
                f"[config] 已将 {self._legacy_var_path.name} 并入 {CONFIG_FILE}"
            )

        if changed:
            self._write(data)

    def _load_legacy_yaml(self) -> dict:
        # 延迟导入：YAML 解析器只服务于旧配置迁移
        from ..common.yaml_utils import parse_yaml

        try:
            data = parse_yaml(self._legacy_yaml_path.read_text(encoding="utf-8"))
        except OSError:
            return {}
        return data if isinstance(data, dict) else {}

    def _read_legacy_var_file(self):
        return load_json_file(self._legacy_var_path)

    def _extract_values(self, data: dict) -> dict:
        # 从旧配置中取出已知字段的值
        #
        #     旧结构有两种：`key: {value: x, label: ...}` 的块结构，
        #     以及 `key: x` 的扁平结构（jm 早期格式）。
        values: dict = {}
        for key in self._fields:
            if key not in data:
                continue
            item = data[key]
            if isinstance(item, dict):
                if "value" in item:
                    values[key] = copy.deepcopy(item["value"])
            else:
                values[key] = copy.deepcopy(item)
        return values

    def _extract_variables(self, raw) -> dict:
        # 变量段统一为 {name: {desc, default, show}}
        result: dict = {}

        # 旧 var_config.json：{"variables": [{"name": ..., ...}]}
        if isinstance(raw, dict) and isinstance(raw.get(VARIABLES_KEY), list):
            raw = raw[VARIABLES_KEY]

        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict) or not entry.get("name"):
                    continue
                result[str(entry["name"])] = {
                    "desc": str(entry.get("desc") or ""),
                    "default": str(entry.get("default") or ""),
                    "show": bool(entry.get("show", True)),
                }
            return result

        if isinstance(raw, dict):
            for name, item in raw.items():
                if isinstance(item, dict):
                    result[str(name)] = {
                        "desc": str(item.get("desc") or ""),
                        "default": str(item.get("default") or ""),
                        "show": bool(item.get("show", True)),
                    }
                elif isinstance(item, str):
                    result[str(name)] = {"desc": item, "default": "", "show": True}

        return result

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

    #  读取

    def _read_raw(self) -> dict:
        data = load_json_file(self._path)
        return data if isinstance(data, dict) else {}

    def _read(self) -> dict:
        self._prepare()
        return self._read_raw()

    def fields(self) -> list[dict]:
        # 字段定义（label/type/hint/default），顺序来自模块 config.py
        result: list[dict] = []
        for key, meta in self._fields.items():
            field = {"key": key}
            field.update(
                {k: copy.deepcopy(v) for k, v in meta.items() if k != "default"}
            )
            field["default"] = copy.deepcopy(meta.get("default"))
            result.append(field)
        return result

    def values(self) -> dict:
        # 字段值：用户配置优先，缺项回退默认值
        data = self._read()
        values = self.default_values()

        for key in self._fields:
            if key not in data:
                continue
            item = data[key]
            if not isinstance(item, dict):
                values[key] = copy.deepcopy(item)

        return values

    def variables(self) -> dict:
        # 用户改过的变量配置（name -> {desc, default, show}）
        data = self._read()
        return self._extract_variables(data.get(VARIABLES_KEY))

    def user_values(self) -> dict:
        # 只返回用户显式保存过的值（不含默认值），用于把旧字段迁移到别处
        data = self._read()
        return {
            key: copy.deepcopy(data[key]) for key in self._fields if key in data
        }

    def user_keys(self) -> set[str]:
        # 用户配置里实际存在的全部键（含已删除字段），用于清理过期配置
        return set(self._read())

    #  写入

    def _write(self, data: dict) -> bool:
        # 只写已知字段与 variables 段，顺序与默认配置一致
        payload: dict = {}
        for key in self._fields:
            if key in data:
                payload[key] = data[key]
        if VARIABLES_KEY in data:
            payload[VARIABLES_KEY] = data[VARIABLES_KEY]

        return save_json_file(self._path, payload)

    def save_values(self, values: dict) -> bool:
        data = self._read()
        for key, value in values.items():
            if key in self._fields:
                data[key] = copy.deepcopy(value)
        return self._write(data)

    def remove_values(self, keys) -> bool:
        # 删除用户配置中的指定键（字段迁移到别处后清理旧值）
        data = self._read()
        changed = False
        for key in keys:
            if key in data:
                data.pop(key, None)
                changed = True
        if not changed:
            return True
        return self._write(data)

    def save_variables(self, variables: dict) -> bool:
        data = self._read()
        data[VARIABLES_KEY] = variables
        return self._write(data)

    def reset(self) -> dict:
        # 移除用户值（保留变量配置），返回默认值
        data = self._read()
        for key in self._fields:
            data.pop(key, None)

        if data:
            self._write(data)
        else:
            self._unlink(self._path)

        return self.default_values()