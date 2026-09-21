"""简易 YAML 配置解析（插件内部只读配置专用）

各模块的默认值写在 `modules/<模块>/config.yaml`，结构固定
（两级键值 + 块标量），因此这里用手写解析器，保持零外部依赖。

支持：
  - 两级缩进的键值对
  - 字符串（含引号）、bool、int、float、null 的类型推断
  - 块标量 `|` `|-` `|+` `>` `>-` `>+`
  - `#` 注释与空行
"""

from __future__ import annotations

import re
from pathlib import Path

# 按文件路径缓存解析结果，避免重复读盘
_CACHE: dict[str, dict] = {}

_BLOCK_SCALAR_RE = re.compile(r"^[|>][+-]?$")
_KEY_RE = re.compile(r"^(\w+):\s*(.*)?$")


def _convert_value(value: str):
    """把 YAML 标量字符串转换为合适的 Python 类型

    Args:
        value: YAML 标量字符串。

    Returns:
        bool、int、float、None 或 str。
    """
    if not value:
        return ""

    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~"):
        return None

    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _unquote(value: str) -> str:
    """去掉成对的单引号或双引号

    Args:
        value: 原始字符串。

    Returns:
        去除外层引号后的字符串。
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _read_block_scalar(lines: list[str], start: int, parent_indent: int) -> tuple[str, int]:
    """读取块标量内容

    Args:
        lines: 全部文本行。
        start: 块内容起始行号。
        parent_indent: 父级键的缩进。

    Returns:
        (块内容, 块结束后的行号)。
    """
    block_lines: list[str] = []
    block_base_indent: int | None = None
    i = start

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            block_lines.append("")
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        if indent <= parent_indent:
            break

        if block_base_indent is None:
            block_base_indent = indent
        block_lines.append(line[block_base_indent:])
        i += 1

    return "\n".join(block_lines), i


def _fold_block_scalar(text: str) -> str:
    """按折叠模式（>）合并块标量：空行分段，段内以空格连接

    Args:
        text: 块标量原文。

    Returns:
        折叠后的字符串。
    """
    paragraphs: list[str] = []
    current: list[str] = []

    for line in text.split("\n"):
        if line == "":
            if current:
                paragraphs.append(" ".join(current))
                current = []
        else:
            current.append(line)

    if current:
        paragraphs.append(" ".join(current))

    return "\n".join(paragraphs)


def parse_yaml(text: str) -> dict:
    """解析简易 YAML 文本

    Args:
        text: YAML 文本内容。

    Returns:
        解析后的嵌套字典；无法识别的行会被忽略。
    """
    result: dict = {}
    current_section: str | None = None
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        match = _KEY_RE.match(stripped)
        if not match:
            i += 1
            continue

        key = match.group(1)
        raw_value = match.group(2).strip() if match.group(2) else ""

        # 顶层键
        if indent == 0:
            current_section = key
            result[key] = _convert_value(_unquote(raw_value)) if raw_value else {}
            i += 1
            continue

        if not current_section:
            i += 1
            continue

        section = result.get(current_section)
        if not isinstance(section, dict):
            section = {}
            result[current_section] = section

        # 块标量
        if raw_value and _BLOCK_SCALAR_RE.match(raw_value):
            block_text, i = _read_block_scalar(lines, i + 1, indent)
            section[key] = (
                _fold_block_scalar(block_text) if raw_value.startswith(">") else block_text
            )
            continue

        section[key] = _convert_value(_unquote(raw_value)) if raw_value else {}
        i += 1

    return result


def load_yaml_config(path: Path) -> dict:
    """加载并缓存 YAML 配置文件

    Args:
        path: 配置文件路径。

    Returns:
        解析后的配置字典；文件不存在或读取失败时返回空字典。
    """
    cache_key = str(path)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    data: dict = {}
    try:
        if path.exists():
            data = parse_yaml(path.read_text(encoding="utf-8"))
    except OSError:
        data = {}

    _CACHE[cache_key] = data
    return data


def get_config_value(config: dict, key_path: str, default=None):
    """按点号路径读取配置值

    Args:
        config: 配置字典。
        key_path: 点号分隔的路径，如 "template.default"。
        default: 找不到时的默认值。

    Returns:
        配置值或默认值。
    """
    value = config
    for key in key_path.split("."):
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value
