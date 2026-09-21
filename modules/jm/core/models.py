"""JMComic 下载数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AlbumInfo:
    """漫画信息

    Attributes:
        id: 漫画 ID。
        name: 完整标题（含汉化组、语言、版本等标记）。
        author: 作者（首位）。
        oname: 原始名称（已剥离汉化组等后缀）。
        description: 简介。
        chapter_count: 章节数。
        page_count: 页数；接口未提供时以下载到的图片数为准。
        works: 所属作品系列。
        actors: 登场人物。
        tags: 标签。
    """

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
        """转换为字典（info.json 的内容）

        Returns:
            漫画信息的字典表示。
        """
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
    """下载结果

    Attributes:
        success: 是否成功。
        message: 结果描述。
        album_id: 漫画 ID。
        album_name: 漫画标题。
        album_info: 漫画信息。
        pdf_path: PDF 文件绝对路径。
        pdf_name: PDF 文件名。
        file_size_mb: PDF 大小（MB）。
        image_count: 合成 PDF 时使用的图片数量。
        from_cache: 是否直接使用了本地缓存。
    """

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
        """转换为字典

        Returns:
            下载结果的字典表示。
        """
        result: dict[str, Any] = {
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


# 进度回调签名：callback(current, total, message)
ProgressCallback = Callable[[int, int, str], None]
