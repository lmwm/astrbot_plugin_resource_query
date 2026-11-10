# JM 本地缓存：info.json 与「是否已下载」判定
#
# info.json 是漫画信息的权威来源（schema 2，章节级）：
#   {
#     "schema": 2,
#     "id": "...", "name": "...", "page_count": 50,
#     "chapters": [{"id": "999", "index": "001", "name": "上",
#                   "pages": 25, "images": 25, "downloaded": true}],
#     "download": {"completed": true, "images": 50, "pages": 50, "at": "..."}
#   }
# 文件存在且结构完整时不联网；缺失或旧格式由服务层重新拉取生成，-F 强制重建。
# 已下载判定优先看整体标记，其次要求所有章节都已下载，最后退回图片数比较。

from __future__ import annotations

import json
from datetime import datetime, timezone

from ...common.module_log import module_logger
from .models import AlbumInfo
from .paths import AlbumPaths

logger = module_logger("jm")


class AlbumCache:
    # 负责漫画信息缓存、下载完成标记与本地命中判定

    def __init__(self, paths: AlbumPaths) -> None:
        self._paths = paths

    #  原始 JSON

    def _read_raw(self, album_id: str) -> dict | None:
        info_file = self._paths.info_file(album_id)
        try:
            data = json.loads(info_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _write_raw(self, album_id: str, data: dict) -> None:
        info_file = self._paths.info_file(album_id)
        try:
            info_file.parent.mkdir(parents=True, exist_ok=True)
            info_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning(f"[jm] 写入 info.json 失败: {e}")

    #  漫画信息

    def load_info(self, album_id: str) -> AlbumInfo | None:
        # 只接受 v2 章节级结构；旧文件视为不完整，由服务层重新拉取并生成
        return self._to_info(self._read_raw(album_id), album_id)

    @staticmethod
    def _str_list(value) -> list[str]:
        # info.json 里的列表字段可能缺失或类型不对，统一成字符串列表
        if not isinstance(value, (list, tuple)):
            return []
        return [str(item) for item in value]

    @staticmethod
    def _chapters(value) -> list[dict]:
        # info.json 的 chapters：每章保存 id / index / name / pages / images / downloaded
        if not isinstance(value, (list, tuple)):
            return []
        result = []
        for item in value:
            if not isinstance(item, dict):
                continue
            chapter_id = str(item.get("id") or "").strip()
            index = str(item.get("index") or "").strip()
            if not chapter_id or not index:
                continue
            try:
                pages = int(item.get("pages", 0) or 0)
                images = int(item.get("images", 0) or 0)
            except (TypeError, ValueError):
                pages = images = 0
            result.append(
                {
                    "id": chapter_id,
                    "index": index,
                    "name": str(item.get("name") or ""),
                    "pages": pages,
                    "images": images,
                    "downloaded": item.get("downloaded") is True,
                }
            )
        return result

    @staticmethod
    def _chapter_pages_from_chapters(chapters: list[dict]) -> list[dict]:
        # 前 5 章页数由 chapters 派生，保证旧模板变量仍有值
        return [
            {
                "index": str(item.get("index") or ""),
                "pages": int(item.get("pages", 0) or 0),
            }
            for item in chapters[:5]
        ]

    @staticmethod
    def _to_info(data: dict | None, album_id: str) -> AlbumInfo | None:
        if not data:
            return None

        try:
            if int(data.get("schema", 0) or 0) < 2:
                return None
            chapters = AlbumCache._chapters(data.get("chapters"))
            if not chapters:
                return None

            chapter_lines = AlbumCache._str_list(data.get("chapter_lines"))
            if not chapter_lines:
                chapter_lines = [
                    (
                        f"第{item['index']}话 {item['name']}（id: {item['id']}）"
                        if item["name"]
                        else f"第{item['index']}话（id: {item['id']}）"
                    )
                    for item in chapters
                ]

            info = AlbumInfo(
                id=str(data.get("id", album_id)),
                name=str(data.get("name", "未知")),
                author=str(data.get("author", "未知")),
                oname=str(data.get("oname", "") or ""),
                chapter_count=int(data.get("chapter_count", 0) or 0),
                page_count=int(
                    data.get("page_count", data.get("image_count", 0)) or 0
                ),
                authors=AlbumCache._str_list(data.get("authors")),
                description=str(data.get("description", "") or ""),
                pub_date=str(data.get("pub_date", "") or ""),
                update_date=str(data.get("update_date", "") or ""),
                views=str(data.get("views", "") or ""),
                likes=str(data.get("likes", "") or ""),
                comments=int(
                    data.get("comments", data.get("comment_count", 0)) or 0
                ),
                tags=AlbumCache._str_list(data.get("tags")),
                actors=AlbumCache._str_list(data.get("actors")),
                works=AlbumCache._str_list(data.get("works")),
                url=str(data.get("url", "") or ""),
                cover=str(data.get("cover", "") or ""),
                chapter_lines=chapter_lines,
                chapter_pages=AlbumCache._chapter_pages_from_chapters(chapters),
                chapters=chapters,
            )
        except (TypeError, ValueError):
            return None

        if (
            not info.name
            or info.name == "未知"
            or info.name.startswith(("获取失败", "未知（"))
        ):
            return None

        return info

    def save_info(
        self,
        info: AlbumInfo,
        download: dict | None = None,
        keep_download: bool = True,
    ) -> None:
        # 写入漫画信息；download 给定时一并写入完成标记（一次读盘、一次写盘）
        # keep_download=False 用于 -F 重建：不保留旧的下载标记
        data = info.to_dict()
        if download is not None:
            data["download"] = download
        elif keep_download:
            raw = self._read_raw(info.id) or {}
            if isinstance(raw.get("download"), dict):
                data["download"] = raw["download"]
        self._write_raw(info.id, data)

    def mark_downloaded(
        self,
        info: AlbumInfo,
        image_count: int,
        chapter_counts: dict[str, int] | None = None,
    ) -> None:
        # 下载成功后写入整体与每章的完成标记；chapter_counts 为 {章节序号: 图片数}
        counts = chapter_counts or {}
        for chapter in info.chapters:
            index = str(chapter.get("index") or "")
            count = int(counts.get(index, 0) or 0)
            if count <= 0:
                continue
            chapter["downloaded"] = True
            chapter["images"] = count
            chapter["pages"] = max(int(chapter.get("pages") or 0), count)

        download = {
            "completed": True,
            "images": max(0, int(image_count)),
            "pages": max(int(info.page_count or 0), int(image_count)),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.save_info(info, download)

    #  本地命中

    def is_downloaded(self, album_id: str, expected_pages: int = 0) -> bool:
        # 已下载：整体标记优先；否则要求所有章节都已下载；再退回图片数判定
        raw = self._read_raw(album_id)
        if isinstance(raw, dict):
            download = raw.get("download")
            if isinstance(download, dict) and download.get("completed") is True:
                return True

            raw_chapters = raw.get("chapters")
            chapters = self._chapters(raw_chapters)
            if (
                isinstance(raw_chapters, list)
                and chapters
                and len(chapters) == len(raw_chapters)
                and all(item["downloaded"] for item in chapters)
            ):
                return True

            if expected_pages <= 0:
                expected_pages = int(raw.get("page_count", 0) or 0)

        if expected_pages <= 0:
            return False

        return self._paths.count_images(album_id) >= expected_pages