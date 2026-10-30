# JM 本地缓存：info.json 与本地 PDF 判定

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import AlbumInfo
from .paths import AlbumPaths

logger = logging.getLogger(__name__)


class AlbumCache:
    # 负责漫画信息缓存与「是否已有可用 PDF」的判定

    def __init__(self, paths: AlbumPaths) -> None:
        self._paths = paths

    def load_info(self, album_id: str) -> AlbumInfo | None:
        # 读取 info.json；名称无效视为无缓存（早期获取失败时会写入占位名称）
        info_file = self._paths.info_file(album_id)
        if not info_file.exists():
            return None

        try:
            data = json.loads(info_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        if not isinstance(data, dict):
            return None

        info = AlbumInfo(
            id=str(data.get("id", album_id)),
            name=str(data.get("name", "未知")),
            author=str(data.get("author", "未知")),
            oname=str(data.get("oname", "") or ""),
            description=str(data.get("description", "") or ""),
            chapter_count=int(data.get("chapter_count", 0) or 0),
            page_count=int(data.get("page_count", data.get("image_count", 0)) or 0),
            works=list(data.get("works", []) or []),
            actors=list(data.get("actors", []) or []),
            tags=list(data.get("tags", []) or []),
        )

        if (
            not info.name
            or info.name == "未知"
            or info.name.startswith(("获取失败", "未知（"))
        ):
            return None

        return info

    def save_info(self, info: AlbumInfo) -> None:
        info_file = self._paths.info_file(info.id)
        try:
            info_file.parent.mkdir(parents=True, exist_ok=True)
            info_file.write_text(
                json.dumps(info.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning(f"[jm] 写入 info.json 失败: {e}")

    def find_pdf(self, album_id: str) -> Path | None:
        # 优先漫画根目录，同时兼容旧结构 pdf/ 与过渡版本 ready/
        root = self._paths.album_root(album_id)
        for pdf_path in sorted(root.glob("*.pdf")):
            return pdf_path
        for pdf_path in sorted((root / "pdf").glob("*.pdf")):
            return pdf_path
        for pdf_path in sorted(
            (self._paths.root / "ready").glob(f"JM{album_id}-*.pdf")
        ):
            return pdf_path
        return None

    def check_local(self, album_id: str) -> dict | None:
        # 返回本地产物信息；无缓存时返回 None
        pdf_path = self.find_pdf(album_id)
        if pdf_path and pdf_path.exists():
            size_mb = pdf_path.stat().st_size / (1024 * 1024)
            return {
                "has_pdf": True,
                "pdf_path": str(pdf_path),
                "pdf_name": pdf_path.name,
                "pdf_size_mb": round(size_mb, 2),
                "album_id": album_id,
            }

        images = self._paths.list_images(album_id)
        if images:
            return {
                "has_pdf": False,
                "has_images": True,
                "image_count": len(images),
                "album_id": album_id,
            }

        return None
