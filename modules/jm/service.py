# JM 下载服务
#
# 负责配置构建、漫画信息获取、下载与 PDF 生成。
# 下载交给 jmcomic 的异步下载器（2.7+），进度直接回到事件循环，
# 不再需要线程池与跨线程调度。本层只产出数据（进度、结果、错误原因），
# 发给用户的消息由模块按模板渲染。
#
# 与 2.7.10 源码对齐的几点：
# - 下载参数写在原生 option.yml 里（见 option.py），不再用代码拼字典；
# - 图片目录按章节分子目录，避免多章节图片同名（都是 00001.jpg）互相覆盖；
# - 用 DownloadResult.manifest.image_filepath_list 拿按章节/页码排好序的图片，
#   旧版无 manifest 的兜底已删除（依赖固定 2.7.10）；
# - check_exception=True 让库抛 PartialDownloadFailedException，不再自己拼错误；
# - 下载阶段保留站点原图（webp/jpg 原样落盘），作为存档；PDF 生成时才按画质
#   转码到临时目录，不覆盖原图。

from __future__ import annotations

import asyncio
from pathlib import Path

from ...common.module_log import module_logger
from . import option as jm_option
from .cache import AlbumCache
from .config import DEFAULT_DOWNLOAD_DIR, OPTION_FIELDS
from .models import AlbumInfo, DownloadResult, ProgressCallback
from .option_default import DIR_RULE as DEFAULT_DIR_RULE
from .paths import AlbumPaths
from .pdf import make_pdf

logger = module_logger("jm")

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

    def __init__(
        self,
        download_dir: str | Path,
        legacy_dir: str | Path | None = None,
        option_file: str | Path | None = None,
    ):
        self.paths = AlbumPaths(download_dir)
        self.cache = AlbumCache(self.paths)
        self._legacy_dir = Path(legacy_dir) if legacy_dir else None
        self._option_file = (
            Path(option_file)
            if option_file
            else self.paths.root.parent / "option.yml"
        )
        # 写入 option.yml 的下载根（相对数据根），bind_config 时更新
        self._download_dir_text = DEFAULT_DOWNLOAD_DIR
        self._ready = False
        self._ready_lock: asyncio.Lock | None = None
        self._config: dict = {}

    #  配置与生命周期

    @property
    def config(self) -> dict:
        # 当前模块配置；由模块在加载与保存后绑定，避免每次下载都读盘
        return self._config

    @property
    def option_file(self) -> Path:
        # option.yml 的位置（与 config.json 同目录，由 Views 表单维护）
        return self._option_file

    @property
    def download_root(self) -> Path:
        # 当前下载根（由 config 的「下载路径」解析而来）
        return self.paths.root

    def bind_config(self, config: dict) -> None:
        self._config = config or {}
        # 下载根固定为数据根下 plugin_data/<插件>/JMDownload，不再读配置
        self._download_dir_text = DEFAULT_DOWNLOAD_DIR
        self.paths.set_normalize_zh(self._config.get("jm_normalize_zh"))

    def set_download_root(self, path: str | Path) -> None:
        # 下载路径变化时重建目录与缓存（路径不变时仍同步繁简设置）
        target = Path(path)
        if self.paths.root == target:
            self.paths.set_normalize_zh(self._config.get("jm_normalize_zh"))
            return
        self.paths = AlbumPaths(target, self._config.get("jm_normalize_zh"))
        self.cache = AlbumCache(self.paths)

    #  下载参数（option.yml）

    def ensure_option_file(self) -> None:
        # 首次加载时生成默认 option.yml；已存在不覆盖
        try:
            jm_option.ensure_file(self._option_file, self._download_dir_text)
        except ImportError as e:
            logger.warning(f"生成 option 配置文件失败（缺依赖）：{e}")

    def read_option_values(self) -> dict:
        # 从 option.yml 读出表单字段的值；缺文件时返回空字典，由字段默认值兜底
        try:
            return jm_option.read_values(self._option_file, OPTION_FIELDS)
        except ImportError as e:
            logger.warning(f"读取 option 配置失败（缺依赖）：{e}")
            return {}

    def update_option_values(self, values: dict) -> None:
        # 把 Views 保存的下载参数写回 option.yml
        if not values:
            return
        try:
            jm_option.update_values(self._option_file, OPTION_FIELDS, values)
        except FileNotFoundError as e:
            logger.warning(f"写入 option 配置失败：{e}")
        except ImportError as e:
            logger.warning(f"写入 option 配置失败（缺依赖）：{e}")

    def reset_option_file(self, base_dir_text: str | None = None) -> None:
        # 恢复默认下载参数（Views 的「恢复默认」）
        try:
            jm_option.reset_file(
                self._option_file, base_dir_text or self._download_dir_text
            )
        except ImportError as e:
            logger.warning(f"重置 option 配置失败（缺依赖）：{e}")

    def enforce_fixed_dir(self) -> None:
        # 下载路径与目录规则不再开放配置：文件里被改过就强制写回固定值
        try:
            changed = jm_option.enforce_fixed_dir(
                self._option_file, self._download_dir_text, DEFAULT_DIR_RULE
            )
        except ImportError as e:
            logger.warning(f"校正目录配置失败（缺依赖）：{e}")
            return
        if changed:
            logger.info(f"目录路径/规则已恢复为固定值：{changed}")

    async def ensure_ready(self) -> None:
        # 首次使用时执行一次旧数据迁移（幂等）；文件操作放到线程里，不卡事件循环
        if self._ready:
            return
        if self._ready_lock is None:
            self._ready_lock = asyncio.Lock()

        async with self._ready_lock:
            if self._ready:
                return
            self._ready = True
            self.ensure_option_file()
            if self._legacy_dir is not None:
                try:
                    moved = await asyncio.to_thread(
                        self.paths.migrate_legacy_root, self._legacy_dir
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"旧版下载目录迁移失败：{type(e).__name__}: {e}")
                    return
                if moved:
                    logger.info(f"已迁移 {moved} 个旧版漫画目录")

    #  配置构建

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self._config.get(key, default))
        except (TypeError, ValueError):
            return default

    def _quality(self) -> int:
        return max(1, min(95, self._int("jm_jpeg_quality", 75)))

    def _build_option(self, image_dir: Path, rule: str | None = None):
        # 从 option 文件读取配置；rule 给定时用它决定图片子目录
        self.ensure_option_file()
        if not self._option_file.is_file():
            raise RuntimeError(f"下载失败：option 配置文件不存在：{self._option_file}")
        return jm_option.load_option(self._option_file, image_dir, rule)

    #  本地缓存

    def check_local(self, album_id: str) -> dict | None:
        # 供模块在下载前判断走缓存还是下载（权威判定仍会复用这份结果）
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
        except Exception as e:  # noqa: BLE001
            logger.warning(f"JM{album_id} 获取漫画详情失败：{self._describe_error(e)}")
            return AlbumInfo(id=str(album_id), name=self._describe_error(e))

        info = self._to_info(album_id, album)
        self.cache.save_info(info)
        return info

    async def _fetch_album(self, album_id: str):
        # 仅取详情，不下载：用轻量异步客户端，避免构造完整下载器
        option = self._build_option(self.paths.album_root(album_id))
        client = option.new_jm_async_client()
        try:
            await client.setup()
            return await client.get_album_detail(str(album_id))
        finally:
            await client.close()

    def _dir_rule(self, album_id: str, info: AlbumInfo) -> str:
        # 固定规则：JM<ID>-P<章节序号:03>-<标题>
        # {title} 由模块解析（优先含中文的 oname + 繁简转换），其余 {Xxx} 交给 jmcomic
        title = self.paths.display_title(info)
        return DEFAULT_DIR_RULE.replace(
            "{title}", title.replace("{", "{{").replace("}", "}}")
        )

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
        cached: dict | None = None,
        info: AlbumInfo | None = None,
    ) -> DownloadResult:
        # 下载漫画并生成 PDF；本方法不抛异常，失败原因放在返回值里
        try:
            import img2pdf  # noqa: F401
            import jmcomic  # noqa: F401
        except ImportError as e:
            logger.error(f"JM{album_id} 依赖导入失败：{e}")
            return DownloadResult(
                success=False, album_id=album_id, error=f"依赖导入失败：{e}"
            )

        await self.ensure_ready()

        if not force:
            if cached is None:
                cached = self.cache.check_local(album_id)
            if cached and cached.get("has_pdf"):
                logger.info(f"JM{album_id} 命中本地缓存：{cached.get('pdf_name')}")
                return DownloadResult(
                    success=True,
                    album_id=album_id,
                    album_info=cached.get("info"),
                    pdf_path=cached.get("pdf_path"),
                    pdf_name=cached.get("pdf_name"),
                    file_size_mb=cached.get("pdf_size_mb", 0),
                    from_cache=True,
                )

        if info is None:
            info = await self.get_album_info(album_id)

        try:
            pdf_path, album_info, image_count, size_mb = await self._run_download(
                album_id, info, progress
            )
        except Exception as e:  # noqa: BLE001
            error = self._describe_error(e)
            logger.error(f"JM{album_id} 下载失败：{error}")
            return DownloadResult(
                success=False, album_id=album_id, album_info=info, error=error
            )

        logger.info(
            f"JM{album_id} 下载完成：{image_count} 张图片，"
            f"PDF {round(size_mb, 2)} MB"
        )

        return DownloadResult(
            success=True,
            album_id=album_id,
            album_name=album_info.name,
            album_info=album_info,
            pdf_path=str(pdf_path),
            pdf_name=pdf_path.name,
            file_size_mb=round(size_mb, 2),
            image_count=image_count,
        )

    async def _run_download(
        self,
        album_id: str,
        info: AlbumInfo,
        progress: ProgressCallback | None,
    ) -> tuple[Path, AlbumInfo, int, float]:
        import jmcomic

        quality = self._quality()
        # 默认画质对已是 JPEG 的源图直接嵌入；其它画质统一转码
        embed_jpeg = quality == 75
        image_dir = self.paths.ensure_album_root(album_id)
        downloader_cls = _make_progress_downloader(progress, info.page_count)

        result = await jmcomic.download_album_async(
            str(album_id),
            option=self._build_option(image_dir, self._dir_rule(album_id, info)),
            downloader=downloader_cls,
            check_exception=True,
        )

        images = [
            Path(str(path)) for path in (result.manifest.image_filepath_list or [])
        ]
        if not images:
            raise RuntimeError("下载失败：未获取到图片")

        album = result.album
        album_info = self._to_info(album_id, album) if album is not None else info
        # 接口未提供总页数时用实际下载数修正（HTML 端有值，API 端常为 0）
        album_info.page_count = len(images)

        pdf_name = f"JM{album_id}-{self.paths.display_title(album_info)}"
        pdf_path = await asyncio.to_thread(
            make_pdf,
            self.paths.ensure_album_root(album_id),
            pdf_name,
            images,
            quality,
            embed_jpeg,
        )

        await asyncio.to_thread(self.paths.cleanup_legacy_layout, album_id, images)

        try:
            size_mb = pdf_path.stat().st_size / (1024 * 1024)
        except OSError:
            size_mb = 0.0

        self.cache.save_info(album_info)
        self.cache.save_pdf_state(album_id, pdf_path)
        return pdf_path, album_info, len(images), size_mb

    @staticmethod
    def _describe_error(error: Exception) -> str:
        message = _ERROR_MESSAGES.get(type(error).__name__)
        if message:
            return message

        text = str(error)
        # 本层抛出的「下载失败：…」已带前缀，模板里还有「下载失败：」，去重
        if isinstance(error, RuntimeError) and text.startswith("下载失败："):
            return text[len("下载失败：") :]
        return f"{type(error).__name__}: {text}"


def _make_progress_downloader(
    callback: ProgressCallback | None,
    initial_total: int = 0,
):
    # 生成带进度的异步下载器类；回调只报数量，文案与节流由模块负责
    import jmcomic

    class _ProgressDownloader(jmcomic.JmAsyncDownloader):
        def __init__(self, option):
            super().__init__(option)
            self._done = 0
            # 总数未知时只报已下载张数，不在章节开始时逐章累加，
            # 避免多章节尚未全部开始时误报 100%
            self._total = max(0, int(initial_total or 0))

        async def after_image(self, image, img_save_path):
            await super().after_image(image, img_save_path)
            self._done += 1
            if callback is not None:
                await callback(self._done, self._total)

    return _ProgressDownloader
