# JMComic 漫画下载模块
#
# 只负责指令语义与消息编排：解析参数、控制发送顺序、拼消息。
# 目录、缓存、下载与 PDF 由 JMService 负责。
#
# 限制：仅允许私聊使用，避免群内分发大文件。

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from astrbot.api.message_components import File
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from ...core.module import ModuleBase
from .service import JMService
from .utils import get_config_fields as _load_config_fields
from .utils import normalize_album_id, pick_display_name

logger = logging.getLogger(__name__)


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class JMModule(ModuleBase):
    # JMComic 漫画下载模块

    def __init__(self, plugin_dir, plugin_name: str) -> None:
        super().__init__(plugin_dir, plugin_name)
        self._service = JMService(
            download_dir=self.get_data_path() / "JMDownload",
            legacy_dir=Path(get_astrbot_data_path()) / "JMDownload",
        )
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_limit = 0

    #  元信息

    @property
    def module_name(self) -> str:
        return "jm"

    @property
    def module_title(self) -> str:
        return "JM 下载"

    @property
    def module_icon(self) -> str:
        return "⇩"

    @property
    def module_desc(self) -> str:
        return "JMComic 漫画下载（仅私聊）"

    #  模块配置

    def get_default_config(self) -> dict:
        from .utils import get_default_config

        return get_default_config()

    def get_config_fields(self) -> list[dict]:
        return _load_config_fields()

    def load_module_config(self) -> dict:
        config = super().load_module_config()
        self._service.bind_config(config)
        return config

    def save_module_config(self, config: dict) -> bool:
        saved = super().save_module_config(config)
        if saved:
            self._service.bind_config(self.load_module_config())
        return saved

    #  指令

    def get_commands(self) -> list[dict]:
        return [{"name": "jm", "desc": "下载 JMComic 漫画：/jm <ID> [redownload]"}]

    async def handle_command(self, command: str, args: list[str], event):
        if command != "jm":
            return

        if event.get_group_id():
            yield event.plain_result("JM 下载仅支持私聊使用，请私聊发送指令")
            return

        if not args:
            yield event.plain_result(
                "用法：/jm <漫画ID> [redownload]\n"
                "例如：/jm 123456\n"
                "添加 redownload 可强制重新下载"
            )
            return

        album_id = normalize_album_id(args[0])
        if album_id is None:
            yield event.plain_result("无效的漫画 ID\n用法：/jm <漫画ID> [redownload]")
            return

        force = len(args) > 1 and args[1].lower() == "redownload"

        self._service.ensure_ready()
        self.load_module_config()

        async for r in self._download_and_send(album_id, event, force):
            yield r

    async def _download_and_send(self, album_id: int, event, force: bool):
        config = self._service.config
        send_file = bool(config.get("jm_send_file", True))
        show_info = bool(config.get("jm_show_info", False))
        info_after = bool(config.get("jm_info_after_download", False))
        max_size_mb = _to_int(config.get("jm_max_file_size", 10), 10)

        info = await self._service.get_album_info(album_id)

        if show_info and not info_after:
            yield event.plain_result(self._info_message(album_id, info))

        if not force:
            cached = self._service.check_local(album_id)
            if cached and cached.get("has_pdf"):
                if show_info and info_after:
                    yield event.plain_result(self._info_message(album_id, info))
                yield event.plain_result(f"JM{album_id} 使用本地缓存…")
                async for r in self._send_pdf(
                    event,
                    cached["pdf_path"],
                    cached["pdf_name"],
                    cached.get("pdf_size_mb", 0),
                    send_file,
                    max_size_mb,
                ):
                    yield r
                return

        yield event.plain_result(f"JM{album_id} 开始下载…")

        progress = self._make_progress_callback(event)

        async with self._get_semaphore():
            result = await self._service.download(
                album_id, progress=progress, force=force
            )

        if not result.success:
            yield event.plain_result(result.message)
            return

        if show_info and info_after:
            yield event.plain_result(self._info_message(album_id, info))

        if not result.pdf_path:
            yield event.plain_result("! 下载完成但未生成 PDF 文件")
            return

        async for r in self._send_pdf(
            event,
            result.pdf_path,
            result.pdf_name or "",
            result.file_size_mb,
            send_file,
            max_size_mb,
        ):
            yield r

    async def _send_pdf(
        self,
        event,
        pdf_path: str,
        pdf_name: str,
        size_mb: float,
        send_file: bool,
        max_size_mb: int,
    ):
        if not send_file:
            yield event.plain_result("√ 下载完成")
            return

        if max_size_mb > 0 and size_mb > max_size_mb:
            yield event.plain_result(
                f"! 文件 {size_mb:.1f} MB 超过上限 {max_size_mb} MB，未发送"
            )
            return

        try:
            yield event.chain_result(
                [File(name=pdf_name or "comic.pdf", file=pdf_path)]
            )
        except Exception as e:
            yield event.plain_result(f"× 发送失败: {e}")

    @staticmethod
    def _info_message(album_id: int, info) -> str:
        # 固定三行（ID / 标题 / 作者），缺失字段用占位符补齐
        author = str(getattr(info, "author", "") or "").strip() or "未知"

        return "\n".join(
            [
                f"I  D：{album_id}",
                f"标题：{JMModule._message_title(info)}",
                f"作者：{author}",
            ]
        )

    @staticmethod
    def _message_title(info) -> str:
        # 消息中优先显示含中文的 oname，否则用完整标题
        title = pick_display_name(
            getattr(info, "oname", ""),
            getattr(info, "name", ""),
        )
        return title or "未知"

    def _make_progress_callback(self, event):
        # 下载器回调在事件循环内执行；这里只投递发送任务，不阻塞图片下载
        async def _callback(current: int, total: int, text: str) -> None:
            asyncio.create_task(self._send_progress(event, text))

        return _callback

    async def _send_progress(self, event, text: str) -> None:
        try:
            await event.send(event.message_result().message(text))
        except Exception:
            pass

    def _get_semaphore(self) -> asyncio.Semaphore:
        # 按配置限制同时下载的漫画数；配置变化时重建
        limit = max(1, _to_int(self._service.config.get("jm_max_concurrent", 1), 1))

        if self._semaphore is None or self._semaphore_limit != limit:
            self._semaphore = asyncio.Semaphore(limit)
            self._semaphore_limit = limit

        return self._semaphore

    #  Views 接口
