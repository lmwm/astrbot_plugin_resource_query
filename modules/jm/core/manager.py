"""JMComic 下载管理器

负责漫画下载、PDF 生成与本地缓存判定。

目录结构（每部漫画一个根目录，PDF 与信息文件与图片目录同级）：

    JMDownload/
    └── JM1083382/
        ├── JM1083382-漫画名称/        ← 下载的图片
        │   ├── 00001.jpg
        │   └── ...
        ├── JM1083382-漫画名称.pdf     ← 生成的 PDF
        └── info.json                  ← 漫画信息缓存

实现要点：
  1. 下载交给 jmcomic 原生下载器，并发 / 代理 / Cookie / 超时 / 重试
     通过 JmOption 下发；目录由 `JM{Aid}-{Atitle}` 规则决定。
  2. 进度通过继承 `JmDownloader` 的 `after_image` 钩子统计，回调在下载线程
     中执行，由调用方负责线程安全转发。
  3. 图片下载与 PDF 生成都在线程池中执行，避免阻塞 AstrBot 事件循环。
  4. 缓存判定兼容历史目录结构（`ready/*.pdf`）。
"""

from __future__ import annotations

import asyncio
import json
import shutil
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from ..utils import pick_display_name
from .models import AlbumInfo, DownloadResult

# 图片文件后缀
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

# Windows 文件名非法字符
_INVALID_FILENAME_CHARS = set('\\/:*?"<>|')

# 历史版本的子目录（新结构启用后不再使用）
_LEGACY_SUBDIRS = ("images", "pdf")

# 进度回调签名：callback(current, total, message)
ProgressCallback = Callable[[int, int, str], None]


class JMManager:
    """JMComic 下载管理器"""

    def __init__(self, config: dict, download_dir: str) -> None:
        """初始化管理器

        Args:
            config: 下载配置（来自 Pages）。
            download_dir: 下载根目录。
        """
        self._config = config or {}
        self._download_dir = Path(download_dir)
        self._download_dir.mkdir(parents=True, exist_ok=True)

    def update_config(self, config: dict) -> None:
        """更新配置

        Args:
            config: 新的配置字典。
        """
        self._config = config or {}

    # ══════════════════════════════════════════
    #  路径
    # ══════════════════════════════════════════

    def album_root(self, album_id: str) -> Path:
        """获取漫画根目录（不创建）

        Args:
            album_id: 漫画 ID。

        Returns:
            形如 `<JMDownload>/JM<ID>` 的目录路径。
        """
        return self._download_dir / f"JM{album_id}"

    def _ensure_album_root(self, album_id: str) -> Path:
        """获取漫画根目录，并确保目录名以大写 `JM` 开头

        Windows 下目录名大小写不敏感，历史遗留的小写目录需要显式改名，
        因此这里做一次规范化后再使用。

        Args:
            album_id: 漫画 ID。

        Returns:
            已存在的漫画根目录。
        """
        target = self.album_root(album_id)

        if target.exists():
            actual = None
            try:
                actual = next(
                    (
                        item
                        for item in self._download_dir.iterdir()
                        if item.is_dir() and item.name.lower() == target.name.lower()
                    ),
                    None,
                )
            except OSError:
                actual = None

            if actual is not None and actual.name != target.name:
                temp = self._download_dir / f"{target.name}__renaming"
                try:
                    actual.rename(temp)
                    temp.rename(target)
                except OSError:
                    pass

        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def display_title(info: AlbumInfo) -> str:
        """选择用于文件与目录命名的标题

        优先使用含中文的简短名（oname），否则退回完整标题，
        并清洗掉 Windows 不允许的字符。

        Args:
            info: 漫画信息。

        Returns:
            清洗后的标题。
        """
        title = pick_display_name(info.oname, info.name)
        return JMManager._safe_name(title) or f"JM{info.id}"

    def image_dir_name(self, album_id: str, info: AlbumInfo) -> str:
        """图片目录名

        Args:
            album_id: 漫画 ID。
            info: 漫画信息。

        Returns:
            形如 `JM<ID>-<标题>` 的目录名。
        """
        return f"JM{album_id}-{self.display_title(info)}"

    def _ensure_image_dir(self, album_id: str, info: AlbumInfo) -> Path:
        """确保图片目录存在并返回

        Args:
            album_id: 漫画 ID。
            info: 漫画信息。

        Returns:
            图片保存目录 `<漫画根目录>/JM<ID>-<标题>`。
        """
        image_dir = self._ensure_album_root(album_id) / self.image_dir_name(album_id, info)
        image_dir.mkdir(parents=True, exist_ok=True)
        return image_dir

    def _info_file(self, album_id: str) -> Path:
        """漫画信息缓存文件路径

        Args:
            album_id: 漫画 ID。

        Returns:
            `<漫画根目录>/info.json`。
        """
        return self.album_root(album_id) / "info.json"

    def _current_image_dir(self, album_id: str) -> Path | None:
        """取该漫画当前使用的图片目录

        命名规则变化后可能残留多个 `JM<ID>-` 目录，此时取最近修改的一个，
        避免同一部漫画的图片被重复收录。

        Args:
            album_id: 漫画 ID。

        Returns:
            图片目录；不存在时返回 None。
        """
        root = self.album_root(album_id)
        if not root.exists():
            return None

        prefix = f"jm{album_id}-"
        try:
            candidates = [
                item
                for item in root.iterdir()
                if item.is_dir() and item.name.lower().startswith(prefix)
            ]
        except OSError:
            return None

        if not candidates:
            return None

        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _list_images(self, album_id: str) -> list[Path]:
        """列出该漫画图片目录中的图片

        只扫描当前使用的图片目录（`JM<ID>-<标题>`），因此历史结构
        （`images/`、旧命名的目录）不会导致 PDF 出现重复页。

        Args:
            album_id: 漫画 ID。

        Returns:
            排序后的图片路径列表。
        """
        target = self._current_image_dir(album_id)
        if target is None:
            return []

        images = [
            path
            for path in target.rglob("*")
            if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES
        ]

        # 同一张图可能残留多种格式（历史 webp 与当前 jpg），
        # 按文件名去重并保留最新的一份
        latest: dict[str, Path] = {}
        for path in images:
            previous = latest.get(path.stem)
            if previous is None or path.stat().st_mtime > previous.stat().st_mtime:
                latest[path.stem] = path

        return sorted(latest.values())

    def _cleanup_legacy_layout(self, album_id: str, keep_dir: Path | None = None) -> None:
        """清理历史遗留目录，避免同一部漫画重复占用磁盘

        清理对象包括旧版结构（`images/`、`pdf/`）以及命名规则变更后
        残留的其它 `JM<ID>-` 目录；仅当保留目录中确实有图片时才执行，
        确保不会误删唯一副本。

        Args:
            album_id: 漫画 ID。
            keep_dir: 需要保留的图片目录；为空时以最新修改的目录为准。
        """
        root = self.album_root(album_id)
        if not root.exists():
            return

        current = keep_dir or self._current_image_dir(album_id)
        if current is None or not self._list_images(album_id):
            return

        for name in _LEGACY_SUBDIRS:
            legacy = root / name
            if legacy.is_dir():
                shutil.rmtree(legacy, ignore_errors=True)

        prefix = f"jm{album_id}-"
        try:
            subdirs = [item for item in root.iterdir() if item.is_dir()]
        except OSError:
            return

        for subdir in subdirs:
            if subdir == current:
                continue
            if subdir.name.lower().startswith(prefix):
                shutil.rmtree(subdir, ignore_errors=True)

    # ══════════════════════════════════════════
    #  配置构建
    # ══════════════════════════════════════════

    def _int(self, key: str, default: int) -> int:
        """读取整数配置项

        Args:
            key: 配置键。
            default: 默认值。

        Returns:
            解析后的整数；非法值返回默认值。
        """
        try:
            return int(self._config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _build_option(self, image_dir: Path):
        """按用户配置构建 jmcomic 的 JmOption

        Args:
            image_dir: 图片保存目录（由调用方算好，不交给 jmcomic 拼名）。

        Returns:
            JmOption 实例。
        """
        import jmcomic

        raw = jmcomic.JmOption.default().deconstruct()

        # 下载并发
        download = raw.setdefault("download", {})
        threading = download.setdefault("threading", {})
        threading["image"] = max(1, self._int("jm_image_threads", 16))
        threading["photo"] = max(1, self._int("jm_photo_threads", 4))

        # 解码后保留站点原图格式（通常为 webp），
        # 生成 PDF 时再由 _compress_images 统一二次压缩为 JPEG。
        download["image"] = {"decode": True}

        # 网络参数
        client = raw.setdefault("client", {})
        client["retry_times"] = max(1, self._int("jm_retry_times", 3))
        client["timeout"] = max(5, self._int("jm_timeout", 20))

        meta = client.setdefault("postman", {}).setdefault("meta_data", {})

        proxy = str(self._config.get("jm_proxy") or "").strip()
        if proxy:
            meta["proxies"] = {"http": proxy, "https": proxy}

        cookies = self._parse_cookies(str(self._config.get("jm_cookies") or ""))
        if cookies:
            meta["cookies"] = cookies

        # 目录规则：直接以 image_dir 作为图片保存目录
        raw["dir_rule"] = {"rule": "Bd", "base_dir": str(image_dir)}

        return jmcomic.JmOption.construct(raw)

    @staticmethod
    def _parse_cookies(raw: str) -> dict[str, str]:
        """把 "k=v; k2=v2" 形式的 Cookie 解析为字典

        Args:
            raw: Cookie 字符串。

        Returns:
            Cookie 字典。
        """
        cookies: dict[str, str] = {}

        for part in raw.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            if key:
                cookies[key] = value.strip()

        return cookies

    # ══════════════════════════════════════════
    #  本地缓存
    # ══════════════════════════════════════════

    def find_pdf(self, album_id: str) -> Path | None:
        """查找该漫画已存在的 PDF

        Args:
            album_id: 漫画 ID。

        Returns:
            PDF 路径；不存在时返回 None。
        """
        for pdf_path in self._iter_pdf(album_id):
            return pdf_path
        return None

    def _iter_pdf(self, album_id: str):
        """遍历该漫画可能的 PDF 路径

        优先新结构（漫画根目录下），并兼容历史版本的 `ready/` 目录。

        Args:
            album_id: 漫画 ID。

        Yields:
            PDF 文件路径。
        """
        root = self.album_root(album_id)
        yield from sorted(root.glob("*.pdf"))
        # 历史结构：<漫画根目录>/pdf/*.pdf
        yield from sorted((root / "pdf").glob("*.pdf"))
        # 过渡版本：<JMDownload>/ready/*.pdf
        yield from sorted((self._download_dir / "ready").glob(f"JM{album_id}-*.pdf"))

    def check_local(self, album_id: str) -> dict | None:
        """检查本地是否已有下载产物

        Args:
            album_id: 漫画 ID。

        Returns:
            含 has_pdf / pdf_path 等字段的字典；无缓存时返回 None。
        """
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

        images = self._list_images(album_id)
        if images:
            return {
                "has_pdf": False,
                "has_images": True,
                "image_count": len(images),
                "album_id": album_id,
            }

        return None

    def _load_cached_info(self, album_id: str) -> AlbumInfo | None:
        """读取本地缓存的漫画信息

        Args:
            album_id: 漫画 ID。

        Returns:
            AlbumInfo；无缓存或损坏时返回 None。
        """
        info_file = self._info_file(album_id)
        if not info_file.exists():
            return None

        try:
            data = json.loads(info_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
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

        # 名称无效说明这条缓存是早期获取失败时写入的，视为无缓存重新获取
        if not info.name or info.name == "未知" or info.name.startswith(("获取失败", "未知（")):
            return None

        return info

    def _save_cached_info(self, info: AlbumInfo) -> None:
        """写入漫画信息缓存

        Args:
            info: 漫画信息。
        """
        info_file = self._info_file(info.id)
        try:
            info_file.parent.mkdir(parents=True, exist_ok=True)
            info_file.write_text(
                json.dumps(info.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ══════════════════════════════════════════
    #  漫画信息
    # ══════════════════════════════════════════

    async def get_album_info(self, album_id: str) -> AlbumInfo:
        """获取漫画信息（优先使用本地缓存）

        Args:
            album_id: 漫画 ID。

        Returns:
            AlbumInfo；获取失败时 name 中带有失败原因。
        """
        cached = self._load_cached_info(album_id)
        if cached:
            return cached

        loop = asyncio.get_running_loop()
        try:
            album = await loop.run_in_executor(None, self._fetch_album, str(album_id))
        except ImportError:
            return AlbumInfo(id=str(album_id), name="未知（jmcomic 未安装）")
        except Exception as e:
            return AlbumInfo(id=str(album_id), name=self._describe_error(e))

        info = AlbumInfo(
            id=str(album_id),
            name=str(getattr(album, "name", "") or "未知"),
            author=str(getattr(album, "author", "") or "未知"),
            oname=str(getattr(album, "oname", "") or ""),
            description=str(getattr(album, "description", "") or ""),
            chapter_count=len(getattr(album, "episode_list", None) or []),
            page_count=int(getattr(album, "page_count", 0) or 0),
            works=list(getattr(album, "works", None) or []),
            actors=list(getattr(album, "actors", None) or []),
            tags=list(getattr(album, "tags", None) or []),
        )
        self._save_cached_info(info)
        return info

    @staticmethod
    def _describe_error(error: Exception) -> str:
        """把下载异常翻译成用户可读的提示

        Args:
            error: 捕获到的异常。

        Returns:
            面向用户的提示文本。
        """
        try:
            from jmcomic.jm_exception import (
                MissingAlbumPhotoException,
                PartialDownloadFailedException,
                RequestRetryAllFailException,
            )
        except ImportError:
            return f"下载失败: {error}"

        if isinstance(error, MissingAlbumPhotoException):
            return "没有找到该漫画，请检查 ID；若内容仅登录可见，请在模块设置中填写 Cookie"

        if isinstance(error, RequestRetryAllFailException):
            return "JMComic 站点连接失败，请稍后重试或在模块设置中配置代理"

        if isinstance(error, PartialDownloadFailedException):
            return "部分图片下载失败，未生成不完整的 PDF，请稍后重试"

        return f"下载失败: {type(error).__name__}: {error}"

    def _fetch_album(self, album_id: str) -> Any:
        """获取 album 详情（同步，需在线程池中调用）

        Args:
            album_id: 漫画 ID。

        Returns:
            jmcomic 的 JmAlbumDetail 对象。
        """
        client = self._build_option(self.album_root(album_id)).build_jm_client()
        return client.get_album_detail(album_id)

    # ══════════════════════════════════════════
    #  下载
    # ══════════════════════════════════════════

    async def download(
        self,
        album_id: str,
        progress_callback: ProgressCallback | None = None,
        force_redownload: bool = False,
    ) -> DownloadResult:
        """下载漫画并生成 PDF

        Args:
            album_id: 漫画 ID。
            progress_callback: 进度回调 (current, total, message)。
            force_redownload: 是否忽略本地缓存强制重新下载。

        Returns:
            DownloadResult。
        """
        try:
            import jmcomic  # noqa: F401
            from img2pdf import convert as img2pdf_convert
        except ImportError as e:
            return DownloadResult(success=False, message=f"缺少依赖: {e}", album_id=album_id)

        if not force_redownload:
            cached = self.check_local(album_id)
            if cached and cached.get("has_pdf"):
                return DownloadResult(
                    success=True,
                    message="使用本地缓存",
                    album_id=album_id,
                    pdf_path=cached.get("pdf_path"),
                    pdf_name=cached.get("pdf_name"),
                    file_size_mb=cached.get("pdf_size_mb", 0),
                    from_cache=True,
                )

        album_info = await self.get_album_info(album_id)
        loop = asyncio.get_running_loop()

        try:
            await loop.run_in_executor(
                None, self._download_images, str(album_id), album_info, progress_callback
            )

            images = self._list_images(str(album_id))
            if not images:
                return DownloadResult(
                    success=False,
                    message="下载失败：未获取到图片",
                    album_id=album_id,
                    album_info=album_info,
                )

            if progress_callback:
                progress_callback(len(images), len(images), "正在生成 PDF...")

            pdf_path = await loop.run_in_executor(
                None,
                self._make_pdf,
                str(album_id),
                album_info,
                images,
                img2pdf_convert,
            )

            # 清理历史目录结构，避免同一漫画重复占用磁盘
            image_dir = self._ensure_image_dir(str(album_id), album_info)
            await loop.run_in_executor(
                None, self._cleanup_legacy_layout, str(album_id), image_dir
            )

            # 用实际下载的图片数修正页数（接口返回的 page_count 常为 0）
            album_info.page_count = len(images)
            self._save_cached_info(album_info)
        except Exception as e:
            return DownloadResult(
                success=False,
                message=self._describe_error(e),
                album_id=album_id,
                album_info=album_info,
            )

        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        return DownloadResult(
            success=True,
            message="下载完成",
            album_id=album_id,
            album_name=album_info.name,
            album_info=album_info,
            pdf_path=str(pdf_path),
            pdf_name=pdf_path.name,
            file_size_mb=round(file_size_mb, 2),
            image_count=len(images),
        )

    def _download_images(
        self,
        album_id: str,
        info: AlbumInfo,
        progress_callback: ProgressCallback | None,
    ) -> None:
        """下载漫画图片（同步，在线程池中执行）

        图片写入 `<漫画根目录>/JM<ID>-<标题>/`。

        Args:
            album_id: 漫画 ID。
            info: 漫画信息（用于决定目录名）。
            progress_callback: 进度回调。
        """
        image_dir = self._ensure_image_dir(album_id, info)
        option = self._build_option(image_dir)
        downloader = _make_progress_downloader(progress_callback)(option)
        downloader.download_album(album_id)

    def _make_pdf(
        self,
        album_id: str,
        album_info: AlbumInfo,
        images: list[Path],
        converter,
    ) -> Path:
        """把图片二次压缩后合成为 PDF（同步，在线程池中执行）

        PDF 放在漫画根目录下，与图片目录同级。

        Args:
            album_id: 漫画 ID。
            album_info: 漫画信息。
            images: 图片路径列表。
            converter: img2pdf 的 convert 函数。

        Returns:
            PDF 文件路径。
        """
        album_root = self._ensure_album_root(album_id)

        # 同一漫画只保留一份 PDF（名称可能随漫画标题变化）
        for old_pdf in album_root.glob("*.pdf"):
            old_pdf.unlink(missing_ok=True)

        quality = max(1, min(95, self._int("jm_jpeg_quality", 75)))
        payloads = self._compress_images(images, quality)

        pdf_name = f"JM{album_id}-{self.display_title(album_info)}"
        pdf_path = album_root / f"{pdf_name}.pdf"
        pdf_path.write_bytes(converter(payloads))
        return pdf_path

    @staticmethod
    def _compress_images(images: list[Path], quality: int) -> list[bytes]:
        """把图片统一二次压缩为 JPEG 字节流

        站点原图多为 webp，PDF 直接嵌入会被无损转码，体积膨胀数倍；
        因此先用 Pillow 按指定质量转成 JPEG，再交给 img2pdf 直接嵌入。
        单张转换失败会被跳过，不影响其余页面。

        Args:
            images: 图片路径列表。
            quality: JPEG 质量（1-95）。

        Returns:
            JPEG 字节流列表。
        """
        from PIL import Image

        payloads: list[bytes] = []

        for path in images:
            try:
                with Image.open(path) as raw:
                    buffer = BytesIO()
                    raw.convert("RGB").save(
                        buffer, format="JPEG", quality=quality, optimize=True
                    )
                payloads.append(buffer.getvalue())
            except Exception:
                continue

        return payloads

    @staticmethod
    def _safe_name(raw: str) -> str:
        """生成安全的文件名

        只剔除 Windows 不允许的字符，保留中英文与方括号等可读字符，
        使 PDF 文件名与图片目录名保持一致。

        Args:
            raw: 原始名称。

        Returns:
            处理后的名称。
        """
        name = "".join(
            "_" if (c in _INVALID_FILENAME_CHARS or ord(c) < 32) else c
            for c in raw[:120]
        )
        return name.strip().strip(".") or "JM"


def _make_progress_downloader(progress_callback: ProgressCallback | None):
    """构造带进度上报的下载器类

    进度通过 jmcomic 的 `after_image` 钩子统计；该钩子在下载线程中执行，
    因此回调实现里不能直接使用 asyncio API。

    Args:
        progress_callback: 进度回调 (current, total, message)。

    Returns:
        JmDownloader 子类（需用 option 实例化）。
    """
    import jmcomic

    class _ProgressDownloader(jmcomic.JmDownloader):
        """在每张图片下载完成后上报进度"""

        def __init__(self, option) -> None:
            super().__init__(option)
            self._done = 0
            self._total = 0

        def before_album(self, album) -> None:
            """记录本子总页数"""
            self._done = 0
            self._total = int(getattr(album, "page_count", 0) or 0)

        def after_image(self, image, img_save_path) -> None:
            """每张图片完成后上报"""
            self._done += 1
            if progress_callback and self._total > 0:
                progress_callback(self._done, self._total, f"下载中 {self._done}/{self._total}")

    return _ProgressDownloader
