# 模块日志：统一写入 AstrBot 日志
#
# 不创建插件自己的日志文件；记录交给 AstrBot 插件 logger，
# 进入 data/logs/astrbot.log 与 WebUI 实时日志。
#
# logger 名称：astrbot.plugin.<插件>.modules.<模块>
# 子 logger 关闭向上传播，改为克隆记录显式转发，确保 AstrBot 的过滤器生效。

from __future__ import annotations

import logging
from pathlib import Path

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


def module_logger(module_name: str) -> logging.Logger:
    # 模块专用 logger：位于 AstrBot 插件 logger 之下，记录统一进 AstrBot 日志
    return logging.getLogger(f"astrbot.plugin.{PLUGIN_NAME}.modules.{module_name}")


def setup_module_logger(module_name: str) -> logging.Logger:
    # 给模块 logger 挂唯一的转发处理器
    #
    #     插件重载后旧处理器对象仍留在 logger 上，且类的身份已变化，
    #     不能靠 isinstance 判断；这里清掉旧的文件/转发处理器再挂一个新的。
    logger = module_logger(module_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        is_old_forward = type(handler).__name__ == "_PluginForwardHandler"
        if isinstance(handler, logging.FileHandler) or is_old_forward:
            logger.removeHandler(handler)
            try:
                handler.close()
            except OSError:
                pass

    forward = _PluginForwardHandler(f"astrbot.plugin.{PLUGIN_NAME}")
    forward.setLevel(logging.INFO)
    forward._plugin_forward = True
    logger.addHandler(forward)

    return logger


def log_separator(logger: logging.Logger, title: str) -> None:
    # 带时间戳的分割线，便于在统一日志里区分每次加载/运行
    logger.info("=" * 24 + f" {title} " + "=" * 24, stacklevel=2)