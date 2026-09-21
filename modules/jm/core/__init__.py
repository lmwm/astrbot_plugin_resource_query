"""JMComic 下载核心层

- JMManager：下载、PDF 生成与本地缓存判定
- AlbumInfo / DownloadResult：数据模型
- ProgressCallback：进度回调类型（current, total, message）
"""

from .manager import JMManager
from .models import AlbumInfo, DownloadResult, ProgressCallback

__all__ = [
    "JMManager",
    "AlbumInfo",
    "DownloadResult",
    "ProgressCallback",
]
