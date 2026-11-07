# JMComic 漫画下载模块
#
# 只负责指令语义与消息编排：解析参数、控制发送顺序、按模块配置里的模板渲染消息。
# 目录、缓存、下载与 PDF 由 JMService 负责；服务只产出数据，不拼用户文案。
#
# 限制：仅允许私聊使用，避免群内分发大文件。

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import ClassVar

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from ...common.module_log import log_separator, module_logger
from ...common.utils import parse_int, render_template
from ...core import dependencies
from ...core.module import ModuleBase
from .config import (
    CONFIG_FIELDS,
    CONFIG_GROUPS,
    DEFAULT_DOWNLOAD_DIR_TEMPLATE,
    OPTION_FIELDS,
    PLUGIN_NAME_TOKEN,
    VAR_SAMPLES,
    VARIABLES,
)
from .models import AlbumInfo, DownloadProgress
from .service import JMService
from .utils import normalize_album_id, pick_display_name

logger = module_logger("jm")

# 指令提示：属于用法说明，不随模板变化
_PRIVATE_ONLY_TEXT = "JM 下载仅支持私聊使用，请私聊发送指令"
_USAGE_SHORT = "用法：/jm [-F] <漫画ID>"
_USAGE_TEXT = (
    f"{_USAGE_SHORT}\n"
    "例如：/jm 123456、/jm -F 123456\n"
    "-F（不区分大小写）表示忽略本地图片与 PDF，全部重新下载"
)
_INVALID_ID_TEXT = f"无效的漫画 ID\n{_USAGE_SHORT}"

# 6.27.0 已删除的配置项；旧 config.json 里可能还留着，加载时清掉
_REMOVED_CONFIG_KEYS = ("jm_download_dir", "jm_dir_rule")


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
        "zhconv": "zhconv",
    }

    def __init__(self, plugin_dir, plugin_name: str) -> None:
        super().__init__(plugin_dir, plugin_name)
        self._data_root = Path(get_astrbot_data_path()).resolve()
        download_dir_text = self._download_dir_text()
        self._service = JMService(
            download_dir=(self._data_root / download_dir_text).resolve(),
            download_dir_text=download_dir_text,
            legacy_dir=self._data_root / "JMDownload",
            option_file=self.get_config_path() / "option.yml",
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
        # 普通字段来自 config.json；下载参数从 option.yml 读入并覆盖同名表单字段
        config = super().load_module_config()
        config.update(self._service.read_option_values())

        # 旧文件里可能残留可配置的规则/路径，统一纠正为固定值
        if self._service.option_file.is_file():
            self._service.enforce_fixed_dir()

        self._service.bind_config(config)
        return config

    def _download_dir_text(self) -> str:
        # 下载根文案（相对数据根）：在这里展开插件名，禁止把 {plugin} 原样落盘
        return DEFAULT_DOWNLOAD_DIR_TEMPLATE.replace(
            PLUGIN_NAME_TOKEN, self._plugin_name
        )

    def save_module_config(self, config: dict) -> bool:
        # 下载参数字段写 option.yml，config.json 只存其余字段
        option_values = {
            key: config[key] for key in OPTION_FIELDS if key in config
        }

        plain = {
            key: value for key, value in config.items() if key not in OPTION_FIELDS
        }

        saved = super().save_module_config(plain)
        if saved:
            self._service.update_option_values(option_values)
            self._service.bind_config(self.load_module_config())
        return saved

    async def api_reset_config(self):
        # 恢复默认：带 group 时只重置当前配置页；不带时兼容旧行为，全部重置
        from astrbot.api.web import json_response, request

        payload = await request.json(default={})
        group = ""
        if isinstance(payload, dict):
            group = str(payload.get("group") or "").strip()

        if group == "option":
            # 下载参数存 option.yml：只把表单字段写回默认值，保留手工加的其它键
            defaults = self._config_store.default_values()
            self._config_store.remove_values(list(OPTION_FIELDS))
            self._service.update_option_values(
                {key: defaults[key] for key in OPTION_FIELDS}
            )
            config = self.load_module_config()
            return json_response(
                {"status": "ok", "config": self.config_payload(config)}
            )

        if group:
            keys = self._group_field_keys(group)
            if keys:
                self._config_store.remove_values(keys)
            config = self.load_module_config()
            return json_response(
                {"status": "ok", "config": self.config_payload(config)}
            )

        self._config_store.reset()
        self._service.reset_option_file()
        config = self.load_module_config()
        return json_response(
            {"status": "ok", "config": self.config_payload(config)}
        )

    #  生命周期

    async def on_load(self) -> None:
        # 插件初始化已统一补装过；这里再复查一次，缺库只记日志，不阻断加载
        await super().on_load()
        self._migrate_option_location()
        self._cleanup_placeholder_dir()
        self._service.ensure_option_file()
        self._migrate_download_params()
        self._service.bind_config(self.load_module_config())
        missing = dependencies.missing(self.required_packages)
        if missing:
            logger.error(
                f"缺少运行依赖：{'、'.join(missing)}；"
                f"未安装的模块：{'、'.join(dependencies.missing_modules(self.required_packages))}，"
                "/jm 只提示安装，不会下载"
            )

    def _migrate_option_location(self) -> None:
        # 6.16.x 的 option.yml 在插件数据根；6.17.0 起与 config.json 同目录
        old = self.get_data_path() / "option.yml"
        new = self._service.option_file
        if old == new or not old.is_file():
            return

        try:
            if not new.is_file():
                new.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old), str(new))
                logger.info(f"已将 option.yml 迁移到 {new.parent.name}/")
                return
            old.unlink()
        except OSError as e:
            logger.warning(f"迁移 option.yml 失败：{type(e).__name__}: {e}")

    def _cleanup_placeholder_dir(self) -> None:
        # 6.27.0 及更早版本构造服务时没展开 {plugin}，会在 plugin_data 下留
        # 字面量 {plugin}/JMDownload 空目录；只删空目录，有内容时保留并提示
        stray = self._data_root / "plugin_data" / PLUGIN_NAME_TOKEN
        if not stray.is_dir():
            return

        try:
            entries = list(stray.iterdir())
            if any(not entry.is_dir() or any(entry.iterdir()) for entry in entries):
                logger.warning(f"残留目录 {stray} 内有文件，未自动删除，请手动确认")
                return
            for entry in entries:
                entry.rmdir()
            stray.rmdir()
        except OSError as e:
            logger.warning(f"清理残留目录失败：{stray}：{type(e).__name__}: {e}")
            return

        logger.info("已清理旧版本残留的空目录：plugin_data/{plugin}")

    def _migrate_download_params(self) -> None:
        # 旧版把下载参数存在 config.json；搬到 option.yml 后删除旧键
        user_values = self._config_store.user_values()
        legacy = {
            key: value for key, value in user_values.items() if key in OPTION_FIELDS
        }
        if legacy:
            self._service.update_option_values(legacy)
            self._config_store.remove_values(list(legacy))
            logger.info(f"已将 {len(legacy)} 个下载参数迁移到 option.yml")

        # 6.27.0 已删除的配置项；旧 config.json 里可能还留着，一并清掉
        removed = [key for key in user_values if key in _REMOVED_CONFIG_KEYS]
        if removed:
            self._config_store.remove_values(removed)
            logger.info(f"已清理过期的 JM 配置项：{'、'.join(removed)}")

    #  指令

    def get_commands(self) -> list[dict]:
        return [{"name": "jm", "desc": "下载 JMComic 漫画：/jm [-F] <ID>"}]

    async def handle_command(self, command: str, args: list[str], event):
        if command != "jm":
            return

        if event.get_group_id():
            yield event.plain_result(_PRIVATE_ONLY_TEXT)
            return

        if not args:
            yield event.plain_result(_USAGE_TEXT)
            return

        album_text, force = self._split_force(args)
        if not album_text:
            yield event.plain_result(_USAGE_TEXT)
            return

        album_id = normalize_album_id(album_text)
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

        await self._service.ensure_ready()

        async for r in self._download_and_send(album_id, event, force):
            yield r

    @staticmethod
    def _split_force(args: list[str]) -> tuple[str, bool]:
        # -F（不区分大小写）写在 ID 前；返回（ID 文本, 是否强制全量重下）
        if args and args[0].lower() == "-f":
            return (args[1] if len(args) > 1 else ""), True
        return (args[0] if args else ""), False

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
        # 配置在加载/保存后已合并默认值；为空时（尚未加载）现读一次
        config = self._service.config or self.load_module_config()

        send_file = bool(config.get("jm_send_file"))
        show_info = bool(config.get("jm_show_info"))
        info_after = bool(config.get("jm_info_after_download"))
        make_pdf_enabled = bool(config.get("jm_make_pdf"))
        max_size_mb = parse_int(config.get("jm_max_file_size"), 0)

        # 缓存命中时完全不请求站点；info.json 无效时缓存层会从 PDF 文件名恢复标题
        cached = self._service.check_local(album_id)
        if not force and cached:
            info = cached["info"]
            variables.update(self._info_variables(album_id, info))
            size_mb = cached["pdf_size_mb"]
            sized = {**variables, "size_mb": f"{size_mb:.1f}"}

            if show_info:
                async for item in self._send_info(event, variables):
                    yield item

            yield event.plain_result(self._render_message("message_cached", sized))

            async for result in self._send_pdf(
                event,
                cached["pdf_path"],
                cached["pdf_name"],
                size_mb,
                send_file,
                max_size_mb,
                sized,
            ):
                yield result
            return

        info = await self._service.get_album_info(album_id, force=force)
        # 章节 ID 会被 jmcomic 重定向到所属本子；后续下载与目录统一用实际本子 ID
        if str(info.id).isdigit() and int(info.id) != album_id:
            album_id = int(info.id)
        variables.update(self._info_variables(album_id, info))

        # 详情在下载前发送
        if show_info and not info_after:
            async for item in self._send_info(event, variables):
                yield item

        yield event.plain_result(self._render_message("message_start", variables))

        reporter = _ProgressReporter(
            event,
            self._progress_text,
            self._progress_interval(info.chapter_count),
        )

        async with self._get_semaphore(config):
            result = await self._service.download(
                album_id,
                progress=reporter.report,
                force=force,
                info=info,
            )

        if not result.success:
            yield event.plain_result(
                self._render_message(
                    "message_error",
                    {**variables, "error": result.error or "未知错误"},
                )
            )
            return

        # 补发最终进度：页数/章节数能看到 50/50、2/2 这类完成状态
        await reporter.flush()

        # 服务侧会用实际下载数与接口详情修正信息，这里同步到模板变量
        if result.album_info is not None:
            variables.update(self._info_variables(album_id, result.album_info))

        if show_info and info_after:
            async for item in self._send_info(event, variables):
                yield item

        if not result.pdf_path:
            if not make_pdf_enabled:
                yield event.plain_result(
                    self._render_message(
                        "message_done", {**variables, "size_mb": "0"}
                    )
                )
            else:
                yield event.plain_result(
                    self._render_message("message_no_pdf", variables)
                )
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

    async def _send_info(self, event, variables: dict):
        # 先发详情文本，再按需附封面图；封面发送失败只记日志，不影响下载流程
        yield event.plain_result(self._render_message("message_info", variables))

        cover = str(variables.get("cover") or "").strip()
        if not cover.startswith("http"):
            return
        try:
            await event.send(MessageChain().url_image(cover))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"发送封面失败：{type(e).__name__}: {e}")

    #  进度

    @staticmethod
    def _progress_interval(chapter_total: int) -> float:
        # 章节越多，进度消息越稀，避免大本子长下载刷屏
        total = max(0, int(chapter_total or 0))
        if total <= 10:
            return 5.0
        if total <= 30:
            return 15.0
        if total <= 60:
            return 30.0
        return 60.0

    def _progress_text(self, progress: DownloadProgress) -> str:
        # 页数按章节统计；章节/页数总数未知时显示 ?
        total = progress.chapter_pages_total
        variables = {
            "chapter_index": (
                str(progress.chapter_index) if progress.chapter_index > 0 else "?"
            ),
            "chapters_total": (
                str(progress.chapters_total) if progress.chapters_total > 0 else "?"
            ),
            "chapters_done": str(progress.chapters_done),
            "chapter_pages_done": str(progress.chapter_pages_done),
            "chapter_pages_total": str(total) if total > 0 else "?",
        }
        key = "message_progress" if total > 0 else "message_progress_count"
        return self._render_message(key, variables)

    #  模板与变量

    def _render_message(self, key: str, variables: dict) -> str:
        # 从模块配置取模板渲染；缺失变量保留 {name} 占位符
        config = self._service.config or self.load_module_config()
        return render_template(config.get(key), variables)

    def _info_variables(self, album_id: int, info: AlbumInfo) -> dict:
        def text(value, default: str = "未知") -> str:
            raw = str(value or "").strip()
            return raw or default

        def date_text(value) -> str:
            raw = text(value)
            return "未知" if raw == "0" else raw

        def join_list(values, default: str = "无", limit: int = 10) -> str:
            items = [str(item).strip() for item in (values or []) if str(item).strip()]
            if not items:
                return default
            if len(items) > limit:
                return "、".join(items[:limit]) + f" …等{len(items)}个"
            return "、".join(items)

        def chapter_text(lines, limit: int = 20) -> str:
            if not lines:
                return "无"
            if len(lines) > limit:
                return (
                    "\n".join(lines[:limit])
                    + f"\n…其余 {len(lines) - limit} 章"
                )
            return "\n".join(lines)

        authors = list(info.authors) or (
            [info.author] if info.author.strip() and info.author != "未知" else []
        )
        chapters = [
            str(item).strip()
            for item in (info.chapter_lines or [])
            if str(item).strip()
        ]
        return {
            "id": str(info.id or album_id),
            "title": self._message_title(info),
            "author": info.author.strip() or "未知",
            "authors": join_list(authors),
            "pages": str(info.page_count) if info.page_count > 0 else "未知",
            "chapters": str(info.chapter_count),
            "url": text(info.url),
            "cover": text(info.cover, ""),
            "pub_date": date_text(info.pub_date),
            "update_date": date_text(info.update_date),
            "views": text(info.views),
            "likes": text(info.likes),
            "comments": str(info.comments),
            "tags": join_list(info.tags),
            "actors": join_list(info.actors),
            "works": join_list(info.works),
            "description": text(info.description, "无"),
            "chapter_list": chapter_text(chapters),
        }

    @staticmethod
    def _message_title(info: AlbumInfo) -> str:
        # 消息中优先显示含中文的 oname，否则用完整标题
        title = pick_display_name(info.oname, info.name)
        return title or "未知"

    #  并发控制

    def _get_semaphore(self, config: dict) -> asyncio.Semaphore:
        # 按配置限制同时下载的漫画数；配置变化时重建
        limit = max(1, parse_int(config.get("jm_max_concurrent"), 2))

        if self._semaphore is None or self._semaphore_limit != limit:
            self._semaphore = asyncio.Semaphore(limit)
            self._semaphore_limit = limit

        return self._semaphore


class _ProgressReporter:
    # 下载进度节流：从下载开始计时，按实例间隔发送（默认 5 秒，章节多时放宽）
    # 用 event.send 直接发送，避免把 MessageEventResult 塞回指令生成器

    _MIN_INTERVAL = 5.0

    def __init__(self, event, render, interval: float | None = None) -> None:
        self._event = event
        self._render = render
        self._interval = float(interval or self._MIN_INTERVAL)
        self._last_at = asyncio.get_running_loop().time()
        self._latest: DownloadProgress | None = None
        self._last_sent: DownloadProgress | None = None
        self._disabled = False
        self._lock = asyncio.Lock()

    async def report(self, progress: DownloadProgress) -> None:
        self._latest = progress
        if self._disabled:
            return

        async with self._lock:
            if self._disabled:
                return

            now = asyncio.get_running_loop().time()
            if now - self._last_at < self._interval:
                return
            await self._send(progress, now)

    async def flush(self) -> None:
        # 下载结束后补发最终快照，确保页数/章节数能看到 完成状态；
        # 本次下载一条进度都没发过时不补，避免短下载多一条消息
        async with self._lock:
            if self._disabled or self._last_sent is None or self._latest is None:
                return
            if self._latest == self._last_sent:
                return
            await self._send(
                self._latest, asyncio.get_running_loop().time()
            )

    async def _send(self, progress: DownloadProgress, now: float) -> None:
        text = self._render(progress)
        try:
            await self._event.send(MessageChain().message(text))
        except Exception as e:  # noqa: BLE001
            self._disabled = True
            logger.warning(
                f"发送进度消息失败，后续进度不再发送："
                f"{type(e).__name__}: {e}"
            )
            return

        self._last_at = now
        self._last_sent = progress
