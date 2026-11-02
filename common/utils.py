# 通用工具函数
#
# 只放与业务无关的通用能力：路径解析、JSON/文本文件读写、文件名规范化。

from __future__ import annotations

import json
import re
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

# 模板占位符：{变量名}
_TEMPLATE_VAR_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def get_data_path(plugin_name: str) -> Path:
    # 获取插件数据目录
    data_path = Path(get_astrbot_data_path()) / "plugin_data" / plugin_name
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path


def get_config_path(plugin_name: str) -> Path:
    # 获取插件配置根目录
    config_path = get_data_path(plugin_name) / "config"
    config_path.mkdir(parents=True, exist_ok=True)
    return config_path


def get_platform_path(plugin_name: str, platform: str) -> Path:
    # 获取指定模块（平台）的配置目录
    platform_path = get_config_path(plugin_name) / platform
    platform_path.mkdir(parents=True, exist_ok=True)
    return platform_path


def get_account_filename(acc: dict, prefix: str = "") -> str:
    # 根据账号信息生成配置文件名
    #
    #     文件名来源优先级：name → account → phone → unnamed，
    #     并过滤掉文件系统不允许的字符。
    name = str(acc.get("name", "") or "").strip()
    if not name:
        name = str(acc.get("account") or acc.get("phone") or "unnamed").strip()

    # 只保留字母、数字、横线、下划线与中文
    name = "".join(c for c in name if c.isalnum() or c in "-_\u4e00-\u9fff")
    if not name:
        name = "unnamed"

    return f"{prefix}{name}.json"


def load_json_file(file_path: Path) -> dict | None:
    # 读取 JSON 文件
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_json_file(file_path: Path, data: dict) -> bool:
    # 写入 JSON 文件
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def load_text_file(file_path: Path) -> str | None:
    # 读取文本文件
    try:
        return file_path.read_text(encoding="utf-8")
    except OSError:
        return None


def save_text_file(file_path: Path, content: str) -> bool:
    # 写入文本文件
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False


def render_template(template: str | None, variables: dict) -> str:
    # 用变量渲染消息模板；缺失的变量保留 {name} 占位符，花括号不合法时原样返回
    text = str(template or "")

    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    try:
        return text.format_map(_SafeDict(variables))
    except (ValueError, IndexError, KeyError):
        return text


def used_template_variables(template: str | None) -> set[str]:
    # 模板里用到的 {变量名}，用于保存前校验变量是否可用
    return set(_TEMPLATE_VAR_RE.findall(str(template or "")))


def parse_int(value, default: int) -> int:
    # 宽松转整数：调用方配置值可能是字符串、空值或非法内容
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
