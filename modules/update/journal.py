# 更新模块的运行日志
#
# 每次执行写一个文件：plugin_data/<插件>/logs/update/<时间戳>_<触发方式>.log
# 只保留最近 KEEP_LOGS 个，避免无限增长。

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 保留的日志文件数量
KEEP_LOGS = 10


class UpdateJournal:
    # 一次更新的日志文件

    def __init__(self, data_dir: Path, keep: int = KEEP_LOGS) -> None:
        self._dir = Path(data_dir) / "logs" / "update"
        self._keep = max(1, int(keep))
        self.path: Path | None = None

    def start(self, trigger: str, current_version: str) -> Path:
        # 开始一次记录；同名秒级冲突时追加序号
        self._dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).astimezone()
        stamp = now.strftime("%Y-%m-%d_%H%M%S")
        path = self._dir / f"{stamp}_{trigger}.log"
        index = 2
        while path.exists():
            path = self._dir / f"{stamp}_{trigger}_{index}.log"
            index += 1

        self.path = path
        self.append(
            f"[{now:%Y-%m-%d %H:%M:%S}] trigger={trigger} current={current_version}"
        )
        return path

    def append(self, text: str) -> None:
        # 追加一行；写失败只记 warning，不影响更新流程
        if self.path is None:
            return

        line = text if text.endswith("\n") else text + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line)
        except OSError as e:
            logger.warning(f"[update] 写日志失败: {e}")

    def prune(self) -> None:
        # 只保留最近 KEEP_LOGS 个文件
        try:
            files = sorted(
                self._dir.glob("*.log"), key=lambda path: path.stat().st_mtime
            )
        except OSError:
            return

        for old in files[: -self._keep]:
            try:
                old.unlink()
            except OSError:
                pass
