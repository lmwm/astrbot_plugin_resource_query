# 模块日志：每个模块一份日志文件，追加写入
#
# 文件：plugin_data/<插件>/logs/<模块>.log
# 格式复用 AstrBot：[时间] [Plugin] [级别] [模块:行号]: 内容
# 每行带时间戳；一次插件加载/一次更新运行用分割线隔开。

from __future__ import annotations

import logging
import time
from pathlib import Path


class _PluginFormatter(logging.Formatter):
    # 输出 AstrBot 风格行；logger 名称去掉插件包名前缀
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


def setup_module_logger(
    data_dir: Path, package_name: str, module_name: str
) -> logging.Logger:
    # 给模块命名空间挂追加写的文件处理器；重复调用复用同一个
    #
    #     package_name 是运行时导入名（AstrBot 下形如 data.plugins.<插件名>），
    #     不能直接用插件名，否则子 logger 不会落到这里。
    logger = logging.getLogger(f"{package_name}.modules.{module_name}")
    logger.setLevel(logging.INFO)

    path = Path(data_dir) / "logs" / f"{module_name}.log"
    key = str(path)

    for handler in logger.handlers:
        if getattr(handler, "_plugin_log_path", "") == key:
            return logger

    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(_PluginFormatter(f"{package_name}."))
    handler._plugin_log_path = key
    logger.addHandler(handler)

    return logger


def log_separator(logger: logging.Logger, title: str) -> None:
    # 写一条带时间戳的分割线；来源行号指向调用方
    logger.info("=" * 24 + f" {title} " + "=" * 24, stacklevel=2)