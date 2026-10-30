# 指令辅助：参数解析与帮助文本

from __future__ import annotations


def parse_args(event, command: str) -> list[str]:
    # 取指令后的参数；唤醒前缀已由 AstrBot 剥离，这里只需去掉指令名本身
    parts = event.get_message_str().strip().split()

    if parts and parts[0].lstrip("/").lower() == command.lower():
        parts = parts[1:]

    return parts


def help_text(version: str, modules) -> str:
    # 根据各模块声明的指令生成帮助文本
    lines = [
        f"▤ 资源查询插件 v{version}",
        "────────────────",
        "用法:",
    ]

    for module in modules:
        for command in module.get_commands():
            lines.append(f"  /{command['name']} — {command['desc']}")

    return "\n".join(lines)
