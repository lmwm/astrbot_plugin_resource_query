# JM 模块数据模型

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadProgress:
    # 一次下载进度快照；页数/章节总数为 0 表示未知

    pages_done: int = 0
    pages_total: int = 0
    chapters_done: int = 0
    chapters_total: int = 0


# 进度回调：callback(DownloadProgress)
ProgressCallback = Callable[[DownloadProgress], Awaitable[None]]


@dataclass
class AlbumInfo:
    # 漫画信息；page_count 为 0 表示接口未提供，以实际下载到的图片数为准

    id: str
    name: str
    author: str = "未知"
    oname: str = ""
    chapter_count: int = 0
    page_count: int = 0

    def to_dict(self) -> dict:
        # 转换为 info.json 的内容
        return {
            "id": self.id,
            "name": self.name,
            "oname": self.oname,
            "author": self.author,
            "chapter_count": self.chapter_count,
            "page_count": self.page_count,
        }


@dataclass
class DownloadResult:
    # 下载结果；成功时带 PDF 路径与大小，失败时 error 为可读原因

    success: bool
    album_info: AlbumInfo | None = None
    pdf_path: str | None = None
    pdf_name: str | None = None
    file_size_mb: float = 0.0
    error: str = ""
