# JM 本地缓存：info.json、PDF 状态与本地命中判定
#
# info.json 同时保存漫画信息与最近一次成功生成的 PDF 状态：
#   {"id": "...", "name": "...", "pdf": {"name": "JM123-标题.pdf", "size_mb": 7.7}}
# 命中缓存时先按记录的文件名直接判断，文件被删除才回退到目录扫描，
# 避免每次 /jm 都递归遍历图片目录。

from __future__ import annotations

import json
from pathlib import Path

from ...common.module_log import module_logger
from .models import AlbumInfo
from .paths import AlbumPaths

logger = module_logger("jm")


class AlbumCache:
    # 负责漫画信息缓存、PDF 状态记录与「是否已有可用 PDF」的判定

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

    @staticmethod
    def _info_from_pdf_name(album_id: str, pdf_name: str) -> AlbumInfo:
        # info.json 无效时至少从 PDF 文件名恢复标题，避免缓存命中还要联网
        prefix = f"JM{album_id}-"
        title = ""
        if pdf_name.lower().startswith(prefix.lower()) and pdf_name.lower().endswith(
            ".pdf"
        ):
            title = pdf_name[len(prefix) : -len(".pdf")]
        return AlbumInfo(id=str(album_id), name=title or "未知")

    def save_info(self, info: AlbumInfo, pdf: dict | None = None) -> None:
        # 写入漫画信息；pdf 给定时一并写入最近一次 PDF 状态（一次读盘、一次写盘）
        # 未给 pdf 时保留已有记录，避免先写信息把它冲掉
        data = info.to_dict()
        if pdf is not None:
            data["pdf"] = pdf
        else:
            raw = self._read_raw(info.id) or {}
            if isinstance(raw.get("pdf"), dict):
                data["pdf"] = raw["pdf"]
        self._write_raw(info.id, data)

    def _pdf_from_state(self, raw: dict | None, album_id: str) -> Path | None:
        # 按 info.json 记录的文件名取 PDF；只接受漫画根目录下的裸文件名
        if not isinstance(raw, dict):
            return None

        pdf = raw.get("pdf")
        if not isinstance(pdf, dict):
            return None

        name = str(pdf.get("name") or "").strip()
        if (
            not name
            or name.startswith(".")
            or "/" in name
            or "\\" in name
            or name in {".", ".."}
        ):
            return None

        path = self._paths.album_root(album_id) / name
        return path if path.is_file() else None

    def _scan_pdf(self, album_id: str) -> Path | None:
        # 兼容没有 PDF 状态记录的老目录：根目录 → 旧 pdf/ → 过渡版 ready/
        root = self._paths.album_root(album_id)
        for pdf_path in sorted(root.glob("*.pdf")):
            if pdf_path.is_file():
                return pdf_path
        for pdf_path in sorted((root / "pdf").glob("*.pdf")):
            if pdf_path.is_file():
                return pdf_path
        for pdf_path in sorted(
            (self._paths.root / "ready").glob(f"JM{album_id}-*.pdf")
        ):
            if pdf_path.is_file():
                return pdf_path
        return None

    #  本地命中

    def check_local(self, album_id: str) -> dict | None:
        # 返回本地产物信息；只查 PDF，不再递归统计图片（下载前不需要）
        raw = self._read_raw(album_id)
        pdf_path = self._pdf_from_state(raw, album_id)
        if pdf_path is None:
            pdf_path = self._scan_pdf(album_id)
        if pdf_path is None:
            return None

        try:
            size_mb = round(pdf_path.stat().st_size / (1024 * 1024), 2)
        except OSError:
            return None

        return {
            "pdf_path": str(pdf_path),
            "pdf_name": pdf_path.name,
            "pdf_size_mb": size_mb,
            "info": self._to_info(raw, album_id)
            or self._info_from_pdf_name(album_id, pdf_path.name),
        }
