# JM 本地缓存：info.json 与「是否已下载」判定
#
# info.json 同时保存漫画信息与下载完成标记：
#   {"id": "...", "name": "...", "download": {"completed": true, "images": 26, "pages": 26, "at": "..."}}
# 判定优先看完成标记（下载成功时才写入）；没有标记的目录才递归统计图片数，
# 与信息里的总页数比较，避免每次 /jm 都扫描大目录。

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
        # 读取漫画信息；早期获取失败时写入的占位名称视为无缓存
        return self._to_info(self._read_raw(album_id), album_id)

    @staticmethod
    def _str_list(value) -> list[str]:
        # info.json 里的列表字段可能缺失或类型不对，统一成字符串列表
        if not isinstance(value, (list, tuple)):
            return []
        return [str(item) for item in value]

    @staticmethod
    def _chapter_pages(value) -> list[dict]:
        # info.json 的 chapter_pages：只接受 [{index, pages}] 结构
        if not isinstance(value, (list, tuple)):
            return []
        result = []
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                result.append(
                    {
                        "index": str(item.get("index") or ""),
                        "pages": int(item.get("pages", 0) or 0),
                    }
                )
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _to_info(data: dict | None, album_id: str) -> AlbumInfo | None:
        if not data:
            return None

        try:
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
                chapter_lines=AlbumCache._str_list(data.get("chapter_lines")),
                chapter_pages=AlbumCache._chapter_pages(data.get("chapter_pages")),
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

    def save_info(self, info: AlbumInfo, download: dict | None = None) -> None:
        # 写入漫画信息；download 给定时一并写入完成标记（一次读盘、一次写盘）
        # 未给 download 时保留已有标记，避免更新信息把它冲掉
        data = info.to_dict()
        if download is not None:
            data["download"] = download
        else:
            raw = self._read_raw(info.id) or {}
            if isinstance(raw.get("download"), dict):
                data["download"] = raw["download"]
        self._write_raw(info.id, data)

    def mark_downloaded(self, info: AlbumInfo, image_count: int) -> None:
        # 下载成功后写入完成标记；pages 取接口页数与实际图片数的较大值
        download = {
            "completed": True,
            "images": max(0, int(image_count)),
            "pages": max(int(info.page_count or 0), int(image_count)),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.save_info(info, download)

    #  本地命中

    def is_downloaded(self, album_id: str, expected_pages: int = 0) -> bool:
        # 已下载：完成标记优先；没有标记时按图片数是否达到总页数判定
        raw = self._read_raw(album_id)
        if isinstance(raw, dict):
            download = raw.get("download")
            if isinstance(download, dict) and download.get("completed") is True:
                return True
            if expected_pages <= 0:
                expected_pages = int(raw.get("page_count", 0) or 0)

        if expected_pages <= 0:
            return False

        return self._paths.count_images(album_id) >= expected_pages