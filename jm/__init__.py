"""JMComic 漫画下载模块"""

from .downloader import JMDownloader
from .utils import normalize_album_id
from .core import JMManager, DownloadResult, AlbumInfo, ProgressInfo, ManagerConfig

__all__ = [
    "JMDownloader",
    "normalize_album_id",
    "JMManager",
    "DownloadResult",
    "AlbumInfo",
    "ProgressInfo",
    "ManagerConfig",
]
