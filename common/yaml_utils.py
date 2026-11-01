# 简易 YAML 解析（仅供旧配置迁移）
#
# 5.9.x 及更早版本把模块配置与更新状态写成 YAML；6.0 起改为 JSON。
# 本文件只保留解析能力，供 ConfigStore 与 update 模块把旧文件转成 JSON 时使用，
# 新代码不要再引用；等旧版本用户都完成升级后可以整体删除。
#
# 支持旧文件用到的子集：两级以上缩进键值、字符串/布尔/数字/null 类型推断、
# `|` / `>` 系列块标量、`#` 注释与空行。

from __future__ import annotations

import re

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
            # 带引号的值按字符串处理，避免 "177.40" 被转成 177.4
            if raw_value[0] in "\"'":
                parent[key] = _unquote(raw_value)
            else:
                parent[key] = _convert_value(raw_value)
            i += 1
            continue

        # 空值表示这是一个新的子层级
        child: dict = {}
        parent[key] = child
        stack.append((indent, child))
        i += 1

    return root