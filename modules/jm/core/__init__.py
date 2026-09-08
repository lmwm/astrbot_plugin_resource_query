"""JMComic 核心模块"""

from .manager import JMManager
from .models import AlbumInfo, DownloadResult, ProgressInfo

__all__ = [
    "JMManager",
    "DownloadResult",
    "AlbumInfo",
    "ProgressInfo",
]
