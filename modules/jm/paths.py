# JM 下载目录布局
#
# 每部漫画一个根目录，PDF、info.json 与图片目录同级：
#   JMDownload/
#   └── JM 1083382/                     ← 第一层目录带空格
#       ├── JM1083382-漫画名称/          ← 图片目录沿用原命名
#       ├── JM1083382-漫画名称.pdf
#       └── info.json
#
# 兼容策略：第一层目录允许无空格旧名 `JM<ID>`，由 migrate_legacy_root 改名；
# 图片目录同时认 `JM<ID>-` 与 5.8.0 产生的 `JM <ID>-`。

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .models import AlbumInfo
from .utils import pick_display_name

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_INVALID_FILENAME_CHARS = set('\\/:*?"<>|')
_LEGACY_SUBDIRS = ("images", "pdf")

# 漫画根目录名：`JM 123456`（也匹配无空格的旧命名）
_ALBUM_DIR_RE = re.compile(r"^JM\s*(\d+)$", re.IGNORECASE | re.ASCII)


class AlbumPaths:
    # 负责漫画目录的解析、创建、清理与旧数据迁移

    def __init__(self, download_dir: str | Path) -> None:
        self.root = Path(download_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def album_root(self, album_id: str) -> Path:
        # 漫画根目录（不创建）
        return self.root / f"JM {album_id}"

    def ensure_album_root(self, album_id: str) -> Path:
        # 漫画根目录，并把历史遗留的小写目录名规范为 `JM <ID>`
        target = self.album_root(album_id)

        if target.exists():
            actual = None
            try:
                actual = next(
                    (
                        item
                        for item in self.root.iterdir()
                        if item.is_dir() and item.name.lower() == target.name.lower()
                    ),
                    None,
                )
            except OSError:
                actual = None

            if actual is not None and actual.name != target.name:
                temp = self.root / f"{target.name}__renaming"
                try:
                    actual.rename(temp)
                    temp.rename(target)
                except OSError:
                    pass

        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def display_title(info: AlbumInfo) -> str:
        # 文件与目录命名用的标题：优先含中文的 oname，并清洗非法字符
        title = pick_display_name(info.oname, info.name)
        return AlbumPaths.safe_name(title) or f"JM{info.id}"

    def image_dir_name(self, album_id: str, info: AlbumInfo) -> str:
        return f"JM{album_id}-{self.display_title(info)}"

    def ensure_image_dir(self, album_id: str, info: AlbumInfo) -> Path:
        image_dir = self.ensure_album_root(album_id) / self.image_dir_name(
            album_id, info
        )
        image_dir.mkdir(parents=True, exist_ok=True)
        return image_dir

    def info_file(self, album_id: str) -> Path:
        return self.album_root(album_id) / "info.json"

    def current_image_dir(self, album_id: str) -> Path | None:
        # 该漫画当前使用的图片目录；经历 5.8.0 子项改名时可能有多个，取最近修改的
        root = self.album_root(album_id)
        if not root.exists():
            return None

        prefixes = (f"jm{album_id}-", f"jm {album_id}-")
        try:
            candidates = [
                item
                for item in root.iterdir()
                if item.is_dir() and item.name.lower().startswith(prefixes)
            ]
        except OSError:
            return None

        if not candidates:
            return None

        return max(candidates, key=lambda path: path.stat().st_mtime)

    def list_images(self, album_id: str) -> list[Path]:
        # 当前图片目录里的图片，按文件名去重并保留最新的一份（防 webp/jpg 双份）
        target = self.current_image_dir(album_id)
        if target is None:
            return []

        try:
            images = [
                path
                for path in target.rglob("*")
                if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES
            ]
        except OSError:
            return []

        latest: dict[str, Path] = {}
        for path in images:
            previous = latest.get(path.stem)
            if previous is None:
                latest[path.stem] = path
                continue
            try:
                if path.stat().st_mtime > previous.stat().st_mtime:
                    latest[path.stem] = path
            except OSError:
                continue

        return sorted(latest.values())

    def cleanup_legacy_layout(
        self, album_id: str, keep_dir: Path | None = None
    ) -> None:
        # 清理历史目录：旧版 images/pdf 子目录与命名变化后残留的其它 JM<ID>- 目录
        root = self.album_root(album_id)
        if not root.exists():
            return

        current = keep_dir or self.current_image_dir(album_id)
        if current is None or not self.list_images(album_id):
            return

        for name in _LEGACY_SUBDIRS:
            legacy = root / name
            if legacy.is_dir():
                shutil.rmtree(legacy, ignore_errors=True)

        prefixes = (f"jm{album_id}-", f"jm {album_id}-")
        try:
            subdirs = [item for item in root.iterdir() if item.is_dir()]
        except OSError:
            return

        for subdir in subdirs:
            if subdir == current:
                continue
            if subdir.name.lower().startswith(prefixes):
                shutil.rmtree(subdir, ignore_errors=True)

    def migrate_legacy_root(self, legacy_dir: str | Path) -> int:
        # 把旧版下载根目录（AstrBot 数据根下的 JMDownload）搬入当前根目录
        legacy = Path(legacy_dir)

        try:
            if not legacy.is_dir():
                return 0
            if legacy.resolve() == self.root.resolve():
                return 0
            entries = list(legacy.iterdir())
        except OSError:
            return 0

        moved = 0
        for entry in entries:
            if not entry.is_dir():
                continue

            match = _ALBUM_DIR_RE.match(entry.name)
            if match is None:
                continue

            album_id = match.group(1)
            target = self.album_root(album_id)
            if target.exists():
                continue

            try:
                shutil.move(str(entry), str(target))
            except OSError:
                continue
            moved += 1

        self._migrate_ready_pdfs(legacy)

        for leftover in (legacy / "ready", legacy):
            try:
                leftover.rmdir()
            except OSError:
                pass

        return moved

    def _migrate_ready_pdfs(self, legacy: Path) -> None:
        # 过渡版本的 ready/*.pdf 归位到对应漫画根目录，已有 PDF 时不覆盖
        try:
            pdfs = list((legacy / "ready").glob("*.pdf"))
        except OSError:
            return

        for pdf in pdfs:
            match = _ALBUM_DIR_RE.match(pdf.stem.split("-", 1)[0])
            if match is None:
                continue

            album_id = match.group(1)
            root = self.album_root(album_id)

            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError:
                continue

            if any(root.glob("*.pdf")):
                continue

            title = pdf.stem.split("-", 1)[1] if "-" in pdf.stem else pdf.stem
            try:
                shutil.move(str(pdf), str(root / f"JM{album_id}-{title}.pdf"))
            except OSError:
                continue

    @staticmethod
    def safe_name(raw: str) -> str:
        # 只剔除 Windows 不允许的字符，保留中英文与方括号等可读字符
        name = "".join(
            "_" if (c in _INVALID_FILENAME_CHARS or ord(c) < 32) else c
            for c in raw[:120]
        )
        return name.strip().strip(".") or "JM"
