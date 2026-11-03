# JM 下载目录布局
#
# 每部漫画一个根目录，PDF、info.json 与图片目录同级：
#   JMDownload/
#   └── JM 1083382/                     ← 第一层目录带空格
#       ├── JM1083382-漫画名称/          ← 图片目录
#       │   ├── JP001-212214/            ← 章节子目录（Pindex-Pid）
#       │   └── JP002-212215/
#       ├── JM1083382-漫画名称.pdf
#       └── info.json
#
# 章节子目录解决多章节图片同名（都是 00001.jpg）互相覆盖的问题；
# 兼容策略：第一层目录允许无空格旧名 `JM<ID>`，图片目录同时认 `JM<ID>-`
# 与 5.8.0 产生的 `JM <ID>-`，旧版直接放在图片目录下的扁平图片由清理逻辑移除。

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

    def __init__(self, download_dir: str | Path, normalize_zh: str | None = None) -> None:
        self.root = Path(download_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._normalize_zh = normalize_zh or None

    def set_normalize_zh(self, value: str | None) -> None:
        # 目录/PDF 名的繁简统一（zh-cn / zh-tw / None）
        self._normalize_zh = str(value or "").strip() or None

    def album_root(self, album_id: str) -> Path:
        # 漫画根目录（不创建）
        return self.root / f"JM {album_id}"

    def ensure_album_root(self, album_id: str) -> Path:
        # 漫画根目录；仅在目标不存在时扫描同名大小写变体（兼容 Linux 旧数据）
        target = self.album_root(album_id)

        if not target.exists():
            self._rename_case_variant(target)

        target.mkdir(parents=True, exist_ok=True)
        return target

    def _rename_case_variant(self, target: Path) -> None:
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
            return

        if actual is None or actual.name == target.name:
            return

        temp = self.root / f"{target.name}__renaming"
        try:
            actual.rename(temp)
            temp.rename(target)
        except OSError:
            pass

    def display_title(self, info: AlbumInfo) -> str:
        # 文件与目录命名用的标题：优先含中文的 oname，清洗非法字符后统一繁简
        title = pick_display_name(info.oname, info.name)
        title = self.safe_name(title) or f"JM{info.id}"
        return self._to_zh(title)

    def _to_zh(self, text: str) -> str:
        # 缺 zhconv 或转换失败时保留原文，不影响下载
        if not self._normalize_zh:
            return text
        try:
            import jmcomic
        except ImportError:
            return text
        return jmcomic.JmcomicText.to_zh(text, self._normalize_zh)

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
        # 当前图片目录里的图片（含章节子目录），按相对路径去重并保留最新的一份
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
            try:
                key = str(path.relative_to(target).with_suffix("")).lower()
            except ValueError:
                continue
            previous = latest.get(key)
            if previous is None:
                latest[key] = path
                continue
            try:
                if path.stat().st_mtime > previous.stat().st_mtime:
                    latest[key] = path
            except OSError:
                continue

        return sorted(latest.values(), key=lambda path: str(path).lower())

    def cleanup_legacy_layout(
        self, album_id: str, keep_dir: Path | None = None
    ) -> None:
        # 清理历史目录：旧版 images/pdf 子目录、改名后残留的其它 JM<ID>- 目录，
        # 以及章节子目录启用前直接放在图片目录下的扁平图片
        root = self.album_root(album_id)
        if not root.exists():
            return

        current = keep_dir or self.current_image_dir(album_id)
        if current is None:
            return

        for name in _LEGACY_SUBDIRS:
            legacy = root / name
            if legacy.is_dir():
                shutil.rmtree(legacy, ignore_errors=True)

        prefixes = (f"jm{album_id}-", f"jm {album_id}-")
        try:
            subdirs = [item for item in root.iterdir() if item.is_dir()]
        except OSError:
            subdirs = []

        for subdir in subdirs:
            if subdir == current:
                continue
            if subdir.name.lower().startswith(prefixes):
                shutil.rmtree(subdir, ignore_errors=True)

        self._cleanup_flat_images(current)

    @staticmethod
    def _cleanup_flat_images(image_dir: Path) -> None:
        # 章节子目录存在时，图片目录下直接的旧扁平图片已被取代，可以删除
        try:
            items = list(image_dir.iterdir())
        except OSError:
            return

        if not any(item.is_dir() for item in items):
            return

        for item in items:
            if item.is_file() and item.suffix.lower() in _IMAGE_SUFFIXES:
                try:
                    item.unlink(missing_ok=True)
                except OSError:
                    continue

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
