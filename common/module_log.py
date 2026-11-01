# 模块日志：每模块一份日志文件，同时写入 AstrBot 统一日志
#
# 自建文件：plugin_data/<插件>/logs/<模块>.log（追加，每次运行前后留空行）
# AstrBot：记录挂到 astrbot.plugin.<插件>.modules.<模块>，会继续写入 AstrBot 日志/WebUI
# 自建文件格式：[时间] [Plugin] [级别] [模块:行号]: 内容

from __future__ import annotations

import logging
import time
from pathlib import Path

from .utils import get_data_path

# 插件目录名即插件名（common/ 的上一级目录）
PLUGIN_NAME = Path(__file__).resolve().parents[1].name


class _PluginForwardHandler(logging.Handler):
    # 把记录交给 AstrBot 插件 logger，让它的过滤器补齐 plugin_tag 等字段
    def __init__(self, target_name: str) -> None:
        super().__init__()
        self._target_name = target_name

    def emit(self, record) -> None:
        target = logging.getLogger(self._target_name)
        clone = logging.makeLogRecord(record.__dict__)
        clone.name = target.name
        target.handle(clone)


class _PluginFormatter(logging.Formatter):
    # 输出 AstrBot 风格行；logger 名称去掉 AstrBot 插件前缀
    def __init__(self, prefix: str) -> None:
        super().__init__()
        self._prefix = prefix

    def formatTime(self, record, datefmt: str | None = None) -> str:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        return f"{stamp}.{int(record.msecs):03d}"

    def format(self, record) -> str:
        name = record.name.removeprefix(self._prefix)
        text = (
            f"[{self.formatTime(record)}] [Plugin] [{record.levelname}] "
            f"[{name}:{record.lineno}]: {record.getMessage()}"
        )
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


def module_logger(module_name: str) -> logging.Logger:
    # 模块专用 logger：位于 AstrBot 插件 logger 之下，既能写自建文件，也进统一日志
    return logging.getLogger(f"astrbot.plugin.{PLUGIN_NAME}.modules.{module_name}")


def setup_module_logger(module_name: str) -> logging.Logger:
    # 给模块 logger 挂文件处理器与转发处理器；重复调用复用同一个
    #
    #     子 logger 不向上传播（父 logger 的过滤器不会对传播记录生效），
    #     而是显式转发一条克隆记录给 AstrBot 插件 logger 处理。
    logger = module_logger(module_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    path = get_data_path(PLUGIN_NAME) / "logs" / f"{module_name}.log"
    key = str(path)

    for handler in logger.handlers:
        if getattr(handler, "_plugin_log_path", "") == key:
            return logger

    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(_PluginFormatter(f"astrbot.plugin.{PLUGIN_NAME}."))
    handler._plugin_log_path = key
    logger.addHandler(handler)

    forward = _PluginForwardHandler(f"astrbot.plugin.{PLUGIN_NAME}")
    forward.setLevel(logging.INFO)
    logger.addHandler(forward)

    return logger


def log_separator(logger: logging.Logger, title: str) -> None:
    # 空行 + 带时间戳的分割线 + 空行，便于区分每次加载/运行
    logger.info("\n" + "=" * 24 + f" {title} " + "=" * 24 + "\n", stacklevel=2)