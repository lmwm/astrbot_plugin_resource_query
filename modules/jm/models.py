# JM 模块数据模型

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

# 进度回调：callback(已下载数, 总数（0 表示未知）, 进度文本)
ProgressCallback = Callable[[int, int, str], Awaitable[None]]


@dataclass
class AlbumInfo:
    # 漫画信息；page_count 为 0 表示接口未提供，以实际下载到的图片数为准

    id: str
    name: str
    author: str = "未知"
    oname: str = ""
    description: str = ""
    chapter_count: int = 0
    page_count: int = 0
    works: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        # 转换为 info.json 的内容
        return {
            "id": self.id,
            "name": self.name,
            "oname": self.oname,
            "author": self.author,
            "description": self.description,
            "chapter_count": self.chapter_count,
            "page_count": self.page_count,
            "works": self.works,
            "actors": self.actors,
            "tags": self.tags,
        }


@dataclass
class DownloadResult:
    # 下载结果

    success: bool
    message: str
    album_id: str = ""
    album_name: str = ""
    album_info: AlbumInfo | None = None
    pdf_path: str | None = None
    pdf_name: str | None = None
    file_size_mb: float = 0.0
    image_count: int = 0
    from_cache: bool = False

    def to_dict(self) -> dict:
        result = {
            "success": self.success,
            "message": self.message,
            "album_id": self.album_id,
            "album_name": self.album_name,
            "file_size_mb": self.file_size_mb,
            "image_count": self.image_count,
            "from_cache": self.from_cache,
        }

        if self.album_info:
            result["album_info"] = self.album_info.to_dict()
        if self.pdf_path:
            result["pdf_path"] = self.pdf_path
        if self.pdf_name:
            result["pdf_name"] = self.pdf_name

        return result
