# JMComic 漫画下载模块
#
# 只负责指令语义与消息编排：解析参数、控制发送顺序、按模块配置里的模板渲染消息。
# 目录、缓存、下载与 PDF 由 JMService 负责；服务只产出数据，不拼用户文案。
#
# 限制：仅允许私聊使用，避免群内分发大文件。

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import ClassVar

from astrbot.api.message_components import File
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from ...common.module_log import log_separator, module_logger
from ...common.utils import parse_int, render_template
from ...core import dependencies
from ...core.module import ModuleBase
from .config import CONFIG_FIELDS, CONFIG_GROUPS, VAR_SAMPLES, VARIABLES
from .service import JMService
from .utils import normalize_album_id, pick_display_name

logger = module_logger("jm")

# 指令提示：属于用法说明，不随模板变化
_PRIVATE_ONLY_TEXT = "JM 下载仅支持私聊使用，请私聊发送指令"
_USAGE_TEXT = (
    "用法：/jm <漫画ID> [redownload]\n"
    "例如：/jm 123456\n"
    "添加 redownload 可强制重新下载"
)
_INVALID_ID_TEXT = "无效的漫画 ID\n用法：/jm <漫画ID> [redownload]"


class JMModule(ModuleBase):
    # JMComic 漫画下载模块

    #  默认配置（来自 config.py）

    config_fields = CONFIG_FIELDS
    config_groups = CONFIG_GROUPS
    variable_defaults = VARIABLES
    var_samples = VAR_SAMPLES

    #  运行依赖（插件初始化时统一检查与补装）
    required_packages: ClassVar[dict[str, str]] = {
        "jmcomic": "jmcomic",
        "img2pdf": "img2pdf",
        "PIL": "Pillow",
    }

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

    def load_module_config(self) -> dict:
        config = super().load_module_config()
        self._service.bind_config(config)
        return config

    def save_module_config(self, config: dict) -> bool:
        saved = super().save_module_config(config)
        if saved:
            self._service.bind_config(self.load_module_config())
        return saved

    #  生命周期

    async def on_load(self) -> None:
        # 插件初始化已统一补装过；这里再复查一次，缺库只记日志，不阻断加载
        await super().on_load()
        missing = dependencies.missing(self.required_packages)
        if missing:
            logger.error(
                f"缺少运行依赖：{'、'.join(missing)}；"
                f"未安装的模块：{'、'.join(dependencies.missing_modules(self.required_packages))}，"
                "/jm 只提示安装，不会下载"
            )

    #  指令

    def get_commands(self) -> list[dict]:
        return [{"name": "jm", "desc": "下载 JMComic 漫画：/jm <ID> [redownload]"}]

    async def handle_command(self, command: str, args: list[str], event):
        if command != "jm":
            return

        if event.get_group_id():
            yield event.plain_result(_PRIVATE_ONLY_TEXT)
            return

        if not args:
            yield event.plain_result(_USAGE_TEXT)
            return

        album_id = normalize_album_id(args[0])
        if album_id is None:
            yield event.plain_result(_INVALID_ID_TEXT)
            return

        # 依赖由插件初始化时统一检查与补装；这里只复查，仍缺就提示，不抛 ModuleNotFoundError
        missing = dependencies.missing(self.required_packages)
        if missing:
            logger.error(
                f"拒绝下载 JM{album_id}：缺少运行依赖 "
                f"{'、'.join(missing)}"
                f"（模块 {'、'.join(dependencies.missing_modules(self.required_packages))}）"
            )
            yield event.plain_result(
                self._render_message(
                    "message_missing_deps", {"deps": "、".join(missing)}
                )
            )
            return

        force = len(args) > 1 and args[1].lower() == "redownload"

        self._service.ensure_ready()

        async for r in self._download_and_send(album_id, event, force):
            yield r

    #  流程编排

    async def _download_and_send(self, album_id: int, event, force: bool):
        # 一次下载的完整流程；异常兜底成模板消息，并记录开始/结束分割线
        label = "强制重下" if force else "缓存优先"
        log_separator(logger, f"JM 下载开始：ID {album_id}（{label}）")

        variables = {"id": str(album_id), "title": "未知"}

        try:
            async for result in self._run_flow(album_id, event, force, variables):
                yield result
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
            logger.error(f"JM{album_id} 下载过程异常：{error}")
            yield event.plain_result(
                self._render_message("message_error", {**variables, "error": error})
            )
        finally:
            log_separator(logger, f"JM 下载结束：ID {album_id}")

    async def _run_flow(self, album_id: int, event, force: bool, variables: dict):
        config = self._service.config
        defaults = self._config_store.default_values()

        send_file = bool(config.get("jm_send_file", defaults.get("jm_send_file")))
        show_info = bool(config.get("jm_show_info", defaults.get("jm_show_info")))
        info_after = bool(
            config.get("jm_info_after_download", defaults.get("jm_info_after_download"))
        )
        max_size_mb = parse_int(
            config.get("jm_max_file_size"),
            parse_int(defaults.get("jm_max_file_size"), 0),
        )

        info = await self._service.get_album_info(album_id)
        variables.update(self._info_variables(album_id, info))

        # 详情在下载前发送
        if show_info and not info_after:
            yield event.plain_result(self._render_message("message_info", variables))

        # 命中本地缓存时不再下载，只补发缓存提示与文件
        if not force:
            cached = self._service.check_local(album_id)
            if cached and cached.get("has_pdf"):
                if show_info and info_after:
                    yield event.plain_result(
                        self._render_message("message_info", variables)
                    )

                size_mb = cached.get("pdf_size_mb", 0)
                yield event.plain_result(
                    self._render_message(
                        "message_cached",
                        {**variables, "size_mb": f"{size_mb:.1f}"},
                    )
                )

                async for result in self._send_pdf(
                    event,
                    cached["pdf_path"],
                    cached["pdf_name"],
                    size_mb,
                    send_file,
                    max_size_mb,
                    {**variables, "size_mb": f"{size_mb:.1f}"},
                ):
                    yield result
                return

        yield event.plain_result(self._render_message("message_start", variables))

        progress = self._make_progress_callback(event)

        async with self._get_semaphore(config):
            result = await self._service.download(
                album_id, progress=progress, force=force
            )

        if not result.success:
            yield event.plain_result(
                self._render_message(
                    "message_error",
                    {**variables, "error": result.error or "未知错误"},
                )
            )
            return

        # 服务侧会用实际下载数修正页数，这里同步到模板变量
        if result.album_info is not None:
            variables.update(self._info_variables(album_id, result.album_info))

        if show_info and info_after:
            yield event.plain_result(self._render_message("message_info", variables))

        if not result.pdf_path:
            yield event.plain_result(self._render_message("message_no_pdf", variables))
            return

        async for r in self._send_pdf(
            event,
            result.pdf_path,
            result.pdf_name or "",
            result.file_size_mb,
            send_file,
            max_size_mb,
            {**variables, "size_mb": f"{result.file_size_mb:.1f}"},
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
        variables: dict,
    ):
        if not send_file:
            yield event.plain_result(self._render_message("message_done", variables))
            return

        if max_size_mb > 0 and size_mb > max_size_mb:
            logger.warning(
                f"JM{variables.get('id')} 文件 {size_mb:.1f} MB "
                f"超过上限 {max_size_mb} MB，未发送"
            )
            yield event.plain_result(
                self._render_message(
                    "message_too_large",
                    {
                        **variables,
                        "size_mb": f"{size_mb:.1f}",
                        "max_size_mb": str(max_size_mb),
                    },
                )
            )
            return

        try:
            yield event.chain_result(
                [File(name=pdf_name or "comic.pdf", file=pdf_path)]
            )
            logger.info(f"JM{variables.get('id')} 已发送文件：{pdf_name}")
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
            logger.error(f"JM{variables.get('id')} 发送文件失败：{error}")
            yield event.plain_result(
                self._render_message(
                    "message_send_failed", {**variables, "error": error}
                )
            )

    #  进度

    def _make_progress_callback(self, event):
        # 下载器回调在事件循环内执行；这里只投递发送任务，不阻塞图片下载
        async def _callback(done: int, total: int) -> None:
            text = self._progress_text(done, total)
            if text:
                asyncio.create_task(self._send_text(event, text))

        return _callback

    def _progress_text(self, done: int, total: int) -> str:
        if total > 0:
            percent = int(done / total * 100)
            return self._render_message(
                "message_progress",
                {"percent": str(percent), "done": str(done), "total": str(total)},
            )

        return self._render_message("message_progress_count", {"done": str(done)})

    async def _send_text(self, event, text: str) -> None:
        try:
            await event.send(event.message_result().message(text))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"发送进度消息失败：{type(e).__name__}: {e}")

    #  模板与变量

    def _render_message(self, key: str, variables: dict) -> str:
        # 从模块配置取模板渲染；缺失变量保留 {name} 占位符
        config = self._service.config or self.load_module_config()
        return render_template(config.get(key), variables)

    def _info_variables(self, album_id: int, info) -> dict:
        return {
            "id": str(album_id),
            "title": self._message_title(info),
            "author": str(getattr(info, "author", "") or "").strip() or "未知",
            "pages": str(int(getattr(info, "page_count", 0) or 0)),
            "chapters": str(int(getattr(info, "chapter_count", 0) or 0)),
        }

    @staticmethod
    def _message_title(info) -> str:
        # 消息中优先显示含中文的 oname，否则用完整标题
        title = pick_display_name(
            getattr(info, "oname", ""),
            getattr(info, "name", ""),
        )
        return title or "未知"

    #  并发控制

    def _get_semaphore(self, config: dict) -> asyncio.Semaphore:
        # 按配置限制同时下载的漫画数；配置变化时重建
        defaults = self._config_store.default_values()
        limit = max(
            1,
            parse_int(
                config.get("jm_max_concurrent"),
                parse_int(defaults.get("jm_max_concurrent"), 1),
            ),
        )

        if self._semaphore is None or self._semaphore_limit != limit:
            self._semaphore = asyncio.Semaphore(limit)
            self._semaphore_limit = limit

        return self._semaphore
