# JM 下载服务
#
# 负责配置构建、漫画信息获取、下载与 PDF 生成。
# 下载交给 jmcomic 的异步下载器（2.7+），进度直接回到事件循环，
# 不再需要线程池与跨线程调度。

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .cache import AlbumCache
from .models import AlbumInfo, DownloadResult, ProgressCallback
from .paths import AlbumPaths
from .pdf import make_pdf

logger = logging.getLogger(__name__)

# 异常类名 → 用户可读提示；按类名匹配，避免依赖库内部模块
_ERROR_MESSAGES = {
    "MissingAlbumPhotoException": (
        "没有找到该漫画，请检查 ID；若内容仅登录可见，请在模块设置中填写 Cookie"
    ),
    "RequestRetryAllFailException": (
        "JMComic 站点连接失败，请稍后重试或在模块设置中配置代理"
    ),
    "PartialDownloadFailedException": "部分图片下载失败，未生成不完整的 PDF，请稍后重试",
    "DownloadCancelledException": "下载已取消",
}


class JMService:
    # JM 下载服务：路径、缓存、下载与 PDF 生成都收敛在这里

    def __init__(self, download_dir: str | Path, legacy_dir: str | Path | None = None):
        self.paths = AlbumPaths(download_dir)
        self.cache = AlbumCache(self.paths)
        self._legacy_dir = Path(legacy_dir) if legacy_dir else None
        self._ready = False
        self._config: dict = {}

    #  配置与生命周期

    def bind_config(self, config: dict) -> None:
        # 绑定当前配置；由模块在加载与保存后调用，避免每次下载都读盘
        self._config = config or {}

    def ensure_ready(self) -> None:
        # 首次使用时执行一次旧数据迁移（幂等，不在插件加载期做磁盘操作）
        if self._ready:
            return
        self._ready = True

        if self._legacy_dir is not None:
            moved = self.paths.migrate_legacy_root(self._legacy_dir)
            if moved:
                logger.info(f"[jm] 已迁移 {moved} 个旧版漫画目录")

    #  配置构建

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self._config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _build_option(self, image_dir: Path):
        # 按用户配置构建 JmOption；关闭库日志，避免刷屏 AstrBot 日志
        import jmcomic

        raw = jmcomic.JmOption.default().deconstruct()
        raw["log"] = False

        download = raw.setdefault("download", {})
        download["cache"] = True
        download.setdefault("image", {})["decode"] = True

        threading = download.setdefault("threading", {})
        threading["image"] = max(1, self._int("jm_image_threads", 16))
        threading["photo"] = max(1, self._int("jm_photo_threads", 4))

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

        raw["dir_rule"] = {"rule": "Bd", "base_dir": str(image_dir)}
        return jmcomic.JmOption.construct(raw)

    @staticmethod
    def _parse_cookies(raw: str) -> dict[str, str]:
        cookies: dict[str, str] = {}

        for part in raw.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            if key:
                cookies[key] = value.strip()

        return cookies

    #  本地缓存

    def check_local(self, album_id: str) -> dict | None:
        return self.cache.check_local(album_id)

    #  漫画信息

    async def get_album_info(self, album_id: str) -> AlbumInfo:
        # 优先读 info.json 缓存，未命中时请求站点并写回
        cached = self.cache.load_info(album_id)
        if cached:
            return cached

        try:
            album = await self._fetch_album(album_id)
        except ImportError:
            return AlbumInfo(id=str(album_id), name="未知（jmcomic 未安装）")
        except Exception as e:
            return AlbumInfo(id=str(album_id), name=self._describe_error(e))

        info = self._to_info(album_id, album)
        self.cache.save_info(info)
        return info

    async def _fetch_album(self, album_id: str):
        # 仅取详情，不下载：借用异步下载器的客户端
        import jmcomic

        option = self._build_option(self.paths.ensure_album_root(album_id))
        async with jmcomic.JmAsyncDownloader(option) as downloader:
            return await downloader.client.get_album_detail(str(album_id))

    @staticmethod
    def _to_info(album_id: str, album) -> AlbumInfo:
        return AlbumInfo(
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

    #  下载

    async def download(
        self,
        album_id: str,
        progress: ProgressCallback | None = None,
        force: bool = False,
    ) -> DownloadResult:
        # 下载漫画并生成 PDF；本方法不抛异常，失败信息放在返回值里
        try:
            import img2pdf  # noqa: F401
            import jmcomic  # noqa: F401
        except ImportError as e:
            return DownloadResult(
                success=False, message=f"缺少依赖: {e}", album_id=album_id
            )

        if not force:
            cached = self.cache.check_local(album_id)
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

        info = await self.get_album_info(album_id)

        try:
            pdf_path, image_count = await self._run_download(album_id, info, progress)
        except Exception as e:
            return DownloadResult(
                success=False,
                message=self._describe_error(e),
                album_id=album_id,
                album_info=info,
            )

        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
        return DownloadResult(
            success=True,
            message="下载完成",
            album_id=album_id,
            album_name=info.name,
            album_info=info,
            pdf_path=str(pdf_path),
            pdf_name=pdf_path.name,
            file_size_mb=round(file_size_mb, 2),
            image_count=image_count,
        )

    async def _run_download(
        self,
        album_id: str,
        info: AlbumInfo,
        progress: ProgressCallback | None,
    ) -> tuple[Path, int]:
        import jmcomic

        image_dir = self.paths.ensure_image_dir(album_id, info)
        option = self._build_option(image_dir)
        downloader_cls = _make_progress_downloader(progress, info.page_count)

        _album, downloader = await jmcomic.download_album_async(
            str(album_id),
            option=option,
            downloader=downloader_cls,
            check_exception=False,
        )

        if downloader.has_download_failures:
            raise RuntimeError(
                "下载失败："
                f"{len(downloader.download_failed_image)} 张图片、"
                f"{len(downloader.download_failed_photo)} 个章节未完成"
            )

        images = _collect_images(downloader)
        if not images:
            raise RuntimeError("下载失败：未获取到图片")

        pdf_name = f"JM{album_id}-{self.paths.display_title(info)}"
        pdf_path = await asyncio.to_thread(
            make_pdf,
            self.paths.ensure_album_root(album_id),
            pdf_name,
            images,
            self._int("jm_jpeg_quality", 75),
        )

        await asyncio.to_thread(self.paths.cleanup_legacy_layout, album_id, image_dir)

        # 接口返回的 page_count 常为 0，用实际下载数修正
        info.page_count = len(images)
        self.cache.save_info(info)

        return pdf_path, len(images)

    @staticmethod
    def _describe_error(error: Exception) -> str:
        message = _ERROR_MESSAGES.get(type(error).__name__)
        if message:
            return message
        return f"下载失败: {type(error).__name__}: {error}"


def _collect_images(downloader) -> list[Path]:
    # 从下载器的成功记录里取图片路径，按文件名排序保证页码顺序
    paths: set[Path] = set()

    for photo_map in downloader.download_success_dict.values():
        for items in photo_map.values():
            for save_path, _image in items:
                paths.add(Path(save_path))

    return sorted(paths, key=lambda path: path.name)


def _make_progress_downloader(
    callback: ProgressCallback | None,
    initial_total: int = 0,
):
    # 生成带进度的异步下载器类；回调在事件循环内直接 await
    import jmcomic

    class _ProgressDownloader(jmcomic.JmAsyncDownloader):
        def __init__(self, option):
            super().__init__(option)
            self._done = 0
            self._total = max(0, int(initial_total or 0))
            self._last_percent = -1
            self._reported = False

        async def before_photo(self, photo):
            await super().before_photo(photo)
            if self._total == 0:
                try:
                    self._total += len(photo)
                except TypeError:
                    pass

        async def after_image(self, image, img_save_path):
            await super().after_image(image, img_save_path)
            self._done += 1

            if callback is None:
                return

            if self._total > 0:
                percent = int(self._done / self._total * 100)
                if percent <= self._last_percent:
                    return
                self._last_percent = percent
                text = f"下载中 {percent}%"
            else:
                # 总页数未知时按数量播报，每 10 张一次
                if self._reported and self._done % 10 != 0:
                    return
                self._reported = True
                text = f"已下载 {self._done} 张"

            await callback(self._done, self._total, text)

    return _ProgressDownloader
