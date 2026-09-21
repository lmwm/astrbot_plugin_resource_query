"""JMComic 漫画下载模块

继承 ModuleBase，实现漫画下载与 PDF 发送。

模块只提供「配置 + 指令」两类能力（没有账号与模板），
因此 Pages 只会渲染它的模块设置区，不显示账号管理。

限制：
  - 仅允许私聊使用，避免群内分发大文件。
  - 下载与 PDF 生成都在线程池中执行，不阻塞 AstrBot 事件循环。
"""

from __future__ import annotations

import asyncio

from astrbot.api.message_components import File

from ...core.module import ModuleBase
from .downloader import JMDownloader
from .utils import get_config_fields as _load_config_fields
from .utils import normalize_album_id, pick_display_name


def _to_int(value, default: int) -> int:
    """把配置值安全转换为整数

    Args:
        value: 原始值。
        default: 转换失败时的默认值。

    Returns:
        整数。
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class JMModule(ModuleBase):
    """JMComic 漫画下载模块"""

    def __init__(self, plugin_dir, plugin_name: str) -> None:
        """初始化模块

        Args:
            plugin_dir: 插件目录路径。
            plugin_name: 插件名称。
        """
        super().__init__(plugin_dir, plugin_name)
        self._downloader = JMDownloader(self.get_config_path())
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_limit = 0

    # ══════════════════════════════════════════
    #  元信息
    # ══════════════════════════════════════════

    @property
    def module_name(self) -> str:
        """模块标识"""
        return "jm"

    @property
    def module_title(self) -> str:
        """模块显示名"""
        return "JM 下载"

    @property
    def module_icon(self) -> str:
        """模块图标"""
        return "📚"

    @property
    def module_desc(self) -> str:
        """模块描述"""
        return "JMComic 漫画下载（仅私聊）"

    # ══════════════════════════════════════════
    #  模块配置
    # ══════════════════════════════════════════

    def get_default_config(self) -> dict:
        """模块默认配置

        Returns:
            默认下载配置。
        """
        return self._downloader.load_config()

    def get_config_fields(self) -> list[dict]:
        """模块配置字段定义（来自 modules/jm/config.yaml）

        Returns:
            字段列表。
        """
        return _load_config_fields()

    def save_module_config(self, config: dict) -> bool:
        """保存模块配置并让下载器立即生效

        Args:
            config: 配置字典。

        Returns:
            是否保存成功。
        """
        saved = super().save_module_config(config)
        if saved:
            self._downloader.reload_config()
        return saved

    # ══════════════════════════════════════════
    #  指令
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        """本模块指令列表

        Returns:
            指令定义列表。
        """
        return [{"name": "jm", "desc": "下载 JMComic 漫画：/jm <ID> [redownload]"}]

    async def handle_command(self, command: str, args: list[str], event):
        """处理 /jm 指令

        Args:
            command: 指令名称。
            args: 参数列表。
            event: 消息事件。

        Yields:
            消息结果。
        """
        if command != "jm":
            return

        config = self.load_module_config()

        if not config.get("jm_enabled", True):
            yield event.plain_result("JM 下载功能已关闭，请在网页管理界面启用")
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

        async for r in self._download_and_send(album_id, event, force):
            yield r

    async def _download_and_send(self, album_id: int, event, force: bool):
        """下载漫画并按配置发送

        Args:
            album_id: 漫画 ID。
            event: 消息事件。
            force: 是否强制重新下载。

        Yields:
            消息结果。
        """
        config = self.load_module_config()
        send_file = bool(config.get("jm_send_file", True))
        show_info = bool(config.get("jm_show_info", False))
        max_size_mb = _to_int(config.get("jm_max_file_size", 10), 10)

        info = await self._downloader.get_album_info(album_id)

        # 1) 漫画信息单独一条消息（可在模块设置中关闭）
        if show_info:
            yield event.plain_result(self._info_message(album_id, info))

        # 2) 命中本地缓存时直接发送
        if not force:
            cached = self._downloader.check_local(str(album_id))
            if cached and cached.get("has_pdf"):
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

        # 3) 开始下载
        yield event.plain_result(f"JM{album_id} 开始下载…")

        loop = asyncio.get_running_loop()
        last = {"text": ""}

        def progress(current: int, total: int, message: str) -> None:
            """下载线程中的进度回调，线程安全地转发到事件循环"""
            if total <= 0 or current <= 0:
                return

            text = f"下载中 {int(current / total * 100)}%"
            if text == last["text"]:
                return
            last["text"] = text
            asyncio.run_coroutine_threadsafe(self._send_progress(event, text), loop)

        async with self._get_semaphore():
            result = await self._downloader.download(
                album_id, progress_callback=progress, force_redownload=force
            )

        if not result.get("success"):
            yield event.plain_result(result.get("message", "下载失败"))
            return

        pdf_path = result.get("pdf_path")
        if not pdf_path:
            yield event.plain_result("⚠️ 下载完成但未生成 PDF 文件")
            return

        async for r in self._send_pdf(
            event,
            pdf_path,
            result.get("pdf_name") or "",
            result.get("file_size_mb", 0),
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
        """发送 PDF 文件（含大小上限判断）

        Args:
            event: 消息事件。
            pdf_path: PDF 绝对路径。
            pdf_name: PDF 文件名。
            size_mb: 文件大小（MB）。
            send_file: 是否发送文件。
            max_size_mb: 大小上限（MB），0 表示不限制。

        Yields:
            消息结果。
        """
        if not send_file:
            yield event.plain_result("✅ 下载完成")
            return

        if max_size_mb > 0 and size_mb > max_size_mb:
            yield event.plain_result(
                f"⚠️ 文件 {size_mb:.1f} MB 超过上限 {max_size_mb} MB，未发送"
            )
            return

        try:
            yield event.chain_result([File(name=pdf_name or "comic.pdf", file=pdf_path)])
        except Exception as e:
            yield event.plain_result(f"❌ 发送失败: {e}")

    @staticmethod
    def _info_message(album_id: int, info) -> str:
        """构建漫画信息消息

        标题优先使用简短名；作者取首位；页数与简介为空时不显示该行。

        Args:
            album_id: 漫画 ID。
            info: AlbumInfo 实例。

        Returns:
            多行文本。
        """
        lines = [f"JM{album_id}"]

        title = JMModule._short_title(info)
        if title:
            lines.append(f"标题：{title}")

        author = str(getattr(info, "author", "") or "").strip()
        if author and author != "未知":
            lines.append(f"作者：{author}")

        pages = int(getattr(info, "page_count", 0) or 0)
        if pages:
            lines.append(f"页数：{pages}")

        description = str(getattr(info, "description", "") or "").strip()
        if description:
            lines.append(f"简介：{description}")

        return "\n".join(lines)

    @staticmethod
    def _short_title(info) -> str:
        """消息中显示的简短标题

        优先使用含中文的 oname，否则用完整标题；限制在 20 字符以内。
        消息不是文件名，因此不做非法字符清洗。

        Args:
            info: AlbumInfo 实例。

        Returns:
            截断后的标题。
        """
        title = pick_display_name(
            getattr(info, "oname", ""),
            getattr(info, "name", ""),
        )

        if len(title) > 20:
            title = title[:19] + "…"

        return title

    async def _send_progress(self, event, text: str) -> None:
        """发送进度提示（失败不影响下载）

        Args:
            event: 消息事件。
            text: 提示文本。
        """
        try:
            await event.send(event.message_result().message(text))
        except Exception:
            pass

    def _get_semaphore(self) -> asyncio.Semaphore:
        """获取下载并发信号量（按配置延迟创建）

        Returns:
            asyncio.Semaphore 实例。
        """
        limit = max(1, _to_int(self.load_module_config().get("jm_max_concurrent", 1), 1))

        if self._semaphore is None or self._semaphore_limit != limit:
            self._semaphore = asyncio.Semaphore(limit)
            self._semaphore_limit = limit

        return self._semaphore

    # ══════════════════════════════════════════
    #  Pages 接口
    # ══════════════════════════════════════════

    def get_web_apis(self) -> list[dict]:
        """本模块的 Pages 接口

        Returns:
            接口定义列表。
        """
        return [
            {"path": "config", "handler": self._api_get_config, "methods": ["GET"], "desc": "获取下载配置"},
            {"path": "config", "handler": self._api_save_config, "methods": ["POST"], "desc": "保存下载配置"},
        ]

    async def _api_get_config(self):
        """获取下载配置"""
        from astrbot.api.web import json_response

        return json_response(self.load_module_config())

    async def _api_save_config(self):
        """保存下载配置"""
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        if not isinstance(payload, dict) or not payload:
            return error_response("缺少配置数据")

        config = self.load_module_config()
        config.update(payload)

        if not self.save_module_config(config):
            return error_response("保存失败")

        return json_response({"status": "ok"})
