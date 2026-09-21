"""JMComic 下载管理器

负责漫画下载、PDF 生成与本地缓存判定。

实现要点：
  1. 下载完全交给 jmcomic 原生下载器，用户的并发 / 代理 / Cookie / 超时 /
     重试配置通过 JmOption 下发；不再自行遍历图片（旧实现误把
     `episode_list` 的元组当对象使用，必然抛 AttributeError）。
  2. 进度通过继承 `JmDownloader` 的 `after_image` 钩子统计，回调在下载线程
     中执行，由调用方负责线程安全转发。
  3. 图片下载与 PDF 生成都在线程池中执行，避免阻塞 AstrBot 事件循环。
  4. 缓存判定兼容旧版目录结构（`JMDownload/<jmID>/*.pdf`）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from .models import AlbumInfo, DownloadResult

# 图片文件后缀
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

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
        self._cache_dir = self._download_dir / "cache"
        self._ready_dir = self._download_dir / "ready"

        for directory in (self._download_dir, self._cache_dir, self._ready_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def update_config(self, config: dict) -> None:
        """更新配置

        Args:
            config: 新的配置字典。
        """
        self._config = config or {}

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

    def _build_option(self, base_dir: Path):
        """按用户配置构建 jmcomic 的 JmOption

        Args:
            base_dir: 图片保存根目录。

        Returns:
            JmOption 实例。
        """
        import jmcomic

        raw = jmcomic.JmOption.default().deconstruct()

        # 下载并发
        threading = raw.setdefault("download", {}).setdefault("threading", {})
        threading["image"] = max(1, self._int("jm_image_threads", 16))
        threading["photo"] = max(1, self._int("jm_photo_threads", 4))

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

        # 保存规则：<base_dir>/<album_id>/
        raw["dir_rule"] = {"rule": "Bd_Aid", "base_dir": str(base_dir)}

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
        """遍历该漫画可能的 PDF 路径（新结构优先，兼容旧结构）

        Args:
            album_id: 漫画 ID。

        Yields:
            PDF 文件路径。
        """
        yield from sorted(self._ready_dir.glob(f"JM{album_id}-*.pdf"))

        # 旧版结构：JMDownload/<jmID>/*.pdf
        for legacy in self._download_dir.glob(f"[Jj][Mm]{album_id}"):
            if legacy.is_dir():
                yield from sorted(legacy.glob("*.pdf"))

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

        album_dir = self._cache_dir / str(album_id)
        images = self._list_images(album_dir)
        if images:
            return {
                "has_pdf": False,
                "has_images": True,
                "image_count": len(images),
                "album_id": album_id,
            }

        return None

    def _list_images(self, album_dir: Path) -> list[Path]:
        """列出目录下的图片文件（递归）

        Args:
            album_dir: 漫画图片目录。

        Returns:
            排序后的图片路径列表。
        """
        if not album_dir.exists():
            return []

        return sorted(
            path
            for path in album_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES
        )

    def _info_file(self, album_id: str) -> Path:
        """漫画信息缓存文件路径

        Args:
            album_id: 漫画 ID。

        Returns:
            info.json 路径。
        """
        return self._cache_dir / str(album_id) / "info.json"

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

        return AlbumInfo(
            id=str(data.get("id", album_id)),
            name=str(data.get("name", "未知")),
            author=str(data.get("author", "未知")),
            chapter_count=int(data.get("chapter_count", 0) or 0),
            image_count=int(data.get("image_count", 0) or 0),
            tags=list(data.get("tags", []) or []),
        )

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
            return AlbumInfo(id=str(album_id), name=f"获取失败: {e}")

        info = AlbumInfo(
            id=str(album_id),
            name=str(getattr(album, "name", "") or "未知"),
            author=str(getattr(album, "author", "") or "未知"),
            chapter_count=len(getattr(album, "episode_list", None) or []),
            image_count=int(getattr(album, "page_count", 0) or 0),
            tags=list(getattr(album, "tags", None) or []),
        )
        self._save_cached_info(info)
        return info

    def _fetch_album(self, album_id: str) -> Any:
        """获取 album 详情（同步，需在线程池中调用）

        Args:
            album_id: 漫画 ID。

        Returns:
            jmcomic 的 JmAlbumDetail 对象。
        """
        client = self._build_option(self._cache_dir).build_jm_client()
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
            album_dir = await loop.run_in_executor(
                None, self._download_images, str(album_id), progress_callback
            )
            images = self._list_images(album_dir)
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
        except Exception as e:
            return DownloadResult(
                success=False,
                message=f"下载失败: {e}",
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
        progress_callback: ProgressCallback | None,
    ) -> Path:
        """下载漫画图片（同步，在线程池中执行）

        Args:
            album_id: 漫画 ID。
            progress_callback: 进度回调。

        Returns:
            图片保存目录。
        """
        option = self._build_option(self._cache_dir)
        downloader = _make_progress_downloader(progress_callback)(option)
        downloader.download_album(album_id)

        album_dir = self._cache_dir / str(album_id)
        album_dir.mkdir(parents=True, exist_ok=True)
        return album_dir

    def _make_pdf(
        self,
        album_id: str,
        album_info: AlbumInfo,
        images: list[Path],
        converter,
    ) -> Path:
        """把图片合成为 PDF（同步，在线程池中执行）

        Args:
            album_id: 漫画 ID。
            album_info: 漫画信息。
            images: 图片路径列表。
            converter: img2pdf 的 convert 函数。

        Returns:
            PDF 文件路径。
        """
        pdf_name = self._safe_name(f"JM{album_id}-{album_info.name}")
        pdf_path = self._ready_dir / f"{pdf_name}.pdf"
        pdf_path.write_bytes(converter([str(path) for path in images]))
        return pdf_path

    @staticmethod
    def _safe_name(raw: str) -> str:
        """生成安全的文件名

        Args:
            raw: 原始名称。

        Returns:
            过滤掉非法字符后的名称。
        """
        name = "".join(c for c in raw[:80] if c.isalnum() or c in "-_. ")
        return name.strip() or "JM"


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
