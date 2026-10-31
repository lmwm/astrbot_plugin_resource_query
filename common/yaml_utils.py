# 简易 YAML 配置解析（插件内部只读配置专用）
#
# 各模块的默认值写在 `modules/<模块>/config.yaml`，结构固定
# （两级键值 + 块标量），因此这里用手写解析器，保持零外部依赖。
#
# 支持：
#   - 两级缩进的键值对
#   - 字符串（含引号）、bool、int、float、null 的类型推断
#   - 块标量 `|` `|-` `|+` `>` `>-` `>+`
#   - `#` 注释与空行

from __future__ import annotations

import re
from pathlib import Path

# 按文件路径缓存解析结果，避免重复读盘
_CACHE: dict[str, dict] = {}

_BLOCK_SCALAR_RE = re.compile(r"^[|>][+-]?$")
_KEY_RE = re.compile(r"^(\w+):\s*(.*)?$")


def _convert_value(value: str):
    # 把 YAML 标量字符串转换为合适的 Python 类型
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
    # 去掉成对的单引号或双引号；双引号内按 YAML 约定还原反斜杠转义
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return value


def _read_block_scalar(
    lines: list[str], start: int, parent_indent: int
) -> tuple[str, int]:
    # 读取块标量内容
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
    # 按折叠模式（>）合并块标量：空行分段，段内以空格连接
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
    # 解析简易 YAML 文本
    #
    #     基于缩进栈实现，支持任意层级嵌套（键值对可以一直往下缩进），
    #     以及 `|` / `>` 系列块标量。
    root: dict = {}
    # 栈元素为 (该层缩进, 对应字典)，栈底是根字典
    stack: list[tuple[int, dict]] = [(-1, root)]
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        match = _KEY_RE.match(stripped)
        if not match:
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        key = match.group(1)
        raw_value = match.group(2).strip() if match.group(2) else ""

        # 回退到当前缩进对应的父容器
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        # 块标量
        if raw_value and _BLOCK_SCALAR_RE.match(raw_value):
            block_text, i = _read_block_scalar(lines, i + 1, indent)
            if raw_value.startswith(">"):
                parent[key] = _fold_block_scalar(block_text)
            elif raw_value.endswith("-"):
                # `|-` 去掉末尾换行，避免读回时多出一个空行
                parent[key] = block_text.rstrip("\n")
            else:
                parent[key] = block_text
            continue

        if raw_value:
            parent[key] = _convert_value(_unquote(raw_value))
            i += 1
            continue

        # 空值表示这是一个新的子层级
        child: dict = {}
        parent[key] = child
        stack.append((indent, child))
        i += 1

    return root


def load_yaml_config(path: Path) -> dict:
    # 加载并缓存 YAML 配置文件
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
    # 按点号路径读取配置值
    value = config
    for key in key_path.split("."):
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def dump_yaml(data: dict) -> str:
    # 把扁平的配置字典写成 YAML：标量用引号，多行文本用 `|-` 块标量
    lines: list[str] = []

    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, str):
            if "\n" in value:
                lines.append(f"{key}: |-")
                for part in value.split("\n"):
                    lines.append(f"  {part}" if part else "")
            else:
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{key}: "{escaped}"')
        else:
            lines.append(f'{key}: "{value}"')

    return "\n".join(lines) + "\n"


def save_yaml_file(path, data: dict) -> bool:
    # 把配置字典写成 YAML 文件
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_yaml(data), encoding="utf-8")
        return True
    except OSError:
        return False
