"""JMComic 漫画下载模块"""

from .downloader import JMDownloader
from .utils import normalize_album_id

__all__ = [
    "JMDownloader",
    "normalize_album_id",
]
