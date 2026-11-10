# JM 模块数据模型

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


class JMError(Exception):
    # 流程失败：异常文本就是可以直接发给用户的原因

    pass


@dataclass(frozen=True)
class DownloadProgress:
    # 一次下载进度快照；页数是「当前/最近章节」的页数，总数为 0 表示未知

    chapter_index: int = 0
    chapters_total: int = 0
    chapters_done: int = 0
    chapter_pages_done: int = 0
    chapter_pages_total: int = 0


# 进度回调：callback(DownloadProgress)
ProgressCallback = Callable[[DownloadProgress], Awaitable[None]]


@dataclass
class AlbumInfo:
    # 漫画信息；page_count 为 0 表示接口未提供，以实际下载到的图片数为准
    # chapters 是 info.json 的权威章节列表：id / index / name / pages / images / downloaded

    id: str
    name: str
    author: str = "未知"
    oname: str = ""
    chapter_count: int = 0
    page_count: int = 0
    authors: list[str] = field(default_factory=list)
    description: str = ""
    pub_date: str = ""
    update_date: str = ""
    views: str = ""
    likes: str = ""
    comments: int = 0
    tags: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    works: list[str] = field(default_factory=list)
    url: str = ""
    cover: str = ""
    chapter_lines: list[str] = field(default_factory=list)
    chapter_pages: list[dict] = field(default_factory=list)
    chapters: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        # 转换为 info.json 的内容；schema 标识章节级结构（v2）
        return {
            "schema": 2,
            "id": self.id,
            "name": self.name,
            "oname": self.oname,
            "author": self.author,
            "chapter_count": self.chapter_count,
            "page_count": self.page_count,
            "authors": self.authors,
            "description": self.description,
            "pub_date": self.pub_date,
            "update_date": self.update_date,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "tags": self.tags,
            "actors": self.actors,
            "works": self.works,
            "url": self.url,
            "cover": self.cover,
            "chapter_lines": self.chapter_lines,
            "chapter_pages": self.chapter_pages,
            "chapters": self.chapters,
        }


@dataclass
class DownloadResult:
    # 下载结果；成功时带实际下载的图片数，失败时 error 为可读原因

    success: bool
    album_info: AlbumInfo | None = None
    image_count: int = 0
    error: str = ""