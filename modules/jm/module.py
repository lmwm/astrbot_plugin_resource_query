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
from . import option as jm_option
from .config import (
    CONFIG_FIELDS,
    CONFIG_GROUPS,
    DEFAULT_DIR_RULE,
    DEFAULT_DOWNLOAD_DIR,
    OPTION_FIELDS,
    PLUGIN_NAME_TOKEN,
    VAR_SAMPLES,
    VARIABLES,
    validate_dir_rule,
)
from .models import AlbumInfo
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
        "zhconv": "zhconv",
    }

    def __init__(self, plugin_dir, plugin_name: str) -> None:
        super().__init__(plugin_dir, plugin_name)
        data_root = Path(get_astrbot_data_path())
        self._service = JMService(
            download_dir=data_root / DEFAULT_DOWNLOAD_DIR,
            legacy_dir=data_root / "JMDownload",
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

        raw = str(config.get("jm_download_dir") or "").strip()
        relative, absolute = self._resolve_download_dir(raw)
        config["jm_download_dir"] = relative
        self._service.set_download_root(absolute)

        # 旧文件的绝对路径在读取时换成相对数据根的写法，避免换机器失效
        if relative != raw and self._service.option_file.is_file():
            self._service.update_option_values({"jm_download_dir": relative})

        # 目录规则：表单只显示 Bd 之后的部分，保存时再补回
        rule = str(config.get("jm_dir_rule") or "").strip() or DEFAULT_DIR_RULE
        config["jm_dir_rule"] = self._rule_for_form(rule)

        # 文件里的规则与规范形式不一致时（如历史遗留的 %% 或缺失 Bd）回写修正
        if self._service.option_file.is_file():
            normalized = self._rule_for_option(config["jm_dir_rule"])
            if normalized != rule:
                self._service.update_option_values({"jm_dir_rule": normalized})

        self._service.bind_config(config)
        return config

    def _expand_plugin_token(self, text: str) -> str:
        # {plugin} → 实际插件目录名，改名后配置无需同步修改
        return text.replace(PLUGIN_NAME_TOKEN, self._plugin_name)

    def _shrink_plugin_token(self, text: str) -> str:
        # 实际插件名 → {plugin}，避免把名字写进用户配置
        return text.replace(self._plugin_name, PLUGIN_NAME_TOKEN)

    @staticmethod
    def _rule_for_form(rule: str) -> str:
        # 表单不显示开头的 Bd/（下载根由「下载路径」决定）
        # 顺带清理历史版本误写入的 %% 转义
        text = str(rule or "").strip().replace("\\", "/").replace("%%", "")
        if text.startswith("Bd/"):
            return text[len("Bd/") :]
        return "" if text == "Bd" else text

    @staticmethod
    def _rule_for_option(rule: str) -> str:
        # 表单里的规则 → option.yml 的完整 DSL
        text = str(rule or "").strip().replace("\\", "/").replace("%%", "")
        text = "/".join(part.strip() for part in text.split("/") if part.strip())
        if not text or text == "Bd":
            return "Bd"
        return text if text.startswith("Bd") else f"Bd/{text}"

    def _resolve_download_dir(self, raw: str) -> tuple[str, Path]:
        # 下载路径相对 AstrBot 数据根；绝对路径在数据根内时转相对，越界回退默认
        # 配置里用 {plugin} 占位，解析时替换成实际插件名
        data_root = Path(get_astrbot_data_path()).resolve()
        text = self._expand_plugin_token(str(raw or "").strip().replace("\\", "/"))
        text = text or self._expand_plugin_token(DEFAULT_DOWNLOAD_DIR)

        path = Path(text)
        if path.is_absolute():
            try:
                text = path.resolve().relative_to(data_root).as_posix()
            except ValueError:
                logger.warning(f"下载路径必须位于 AstrBot 数据根内，已回退默认：{path}")
                text = self._expand_plugin_token(DEFAULT_DOWNLOAD_DIR)

        resolved = (data_root / text).resolve()
        try:
            resolved.relative_to(data_root)
        except ValueError:
            logger.warning(f"下载路径越出数据根，已回退默认：{text}")
            text = self._expand_plugin_token(DEFAULT_DOWNLOAD_DIR)
            resolved = (data_root / text).resolve()

        # 写回配置时恢复占位符
        return self._shrink_plugin_token(text), resolved

    def save_module_config(self, config: dict) -> bool:
        # 下载参数字段写 option.yml，config.json 只存其余字段
        option_values = {
            key: config[key] for key in OPTION_FIELDS if key in config
        }
        if "jm_dir_rule" in option_values:
            option_values["jm_dir_rule"] = self._rule_for_option(
                option_values["jm_dir_rule"]
            )

        plain = {
            key: value for key, value in config.items() if key not in OPTION_FIELDS
        }

        saved = super().save_module_config(plain)
        if saved:
            self._service.update_option_values(option_values)
            self._service.bind_config(self.load_module_config())
        return saved

    def validate_config_payload(self, payload: dict) -> str | None:
        # 目录规则校验：补回 Bd 后检查层级与占位符
        rule = payload.get("jm_dir_rule")
        if isinstance(rule, str) and rule.strip():
            problem = validate_dir_rule(self._rule_for_option(rule))
            if problem:
                return problem
        return super().validate_config_payload(payload)

    async def api_reset_config(self):
        # 恢复默认：config.json 与 option.yml 一起重置
        from astrbot.api.web import json_response

        self._config_store.reset()
        self._service.reset_option_file(DEFAULT_DIR_RULE)
        self._service.bind_config(self.load_module_config())
        return json_response(
            {"status": "ok", "config": self.config_payload(self.load_module_config())}
        )

    #  生命周期

    async def on_load(self) -> None:
        # 插件初始化已统一补装过；这里再复查一次，缺库只记日志，不阻断加载
        await super().on_load()
        self._migrate_option_location()
        self._service.ensure_option_file()
        self._migrate_legacy_rule()
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

    def _migrate_legacy_rule(self) -> None:
        # 6.14–6.19 的章节子目录规则改回 Bd（图片直接放图片目录）
        try:
            if jm_option.migrate_legacy_rule(self._service.option_file):
                logger.info("目录规则已改回 Bd（图片不再按章节分子目录）")
        except ImportError:
            pass

    def _migrate_download_params(self) -> None:
        # 旧版把下载参数存在 config.json；搬到 option.yml 后删除旧键
        legacy = {
            key: value
            for key, value in self._config_store.user_values().items()
            if key in OPTION_FIELDS
        }
        if not legacy:
            return

        self._service.update_option_values(legacy)
        self._config_store.remove_values(list(legacy))
        logger.info(f"已将 {len(legacy)} 个下载参数迁移到 option.yml")

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

        await self._service.ensure_ready()

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

        # 缓存命中时完全不请求站点：用 info.json，缺失则从 PDF 文件名取标题
        cached = self._service.check_local(album_id)
        if not force and cached and cached.get("has_pdf"):
            info = cached.get("info") or self._info_from_cached(album_id, cached)
            variables.update(self._info_variables(album_id, info))

            if show_info:
                yield event.plain_result(self._render_message("message_info", variables))

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

        info = await self._service.get_album_info(album_id)
        variables.update(self._info_variables(album_id, info))

        # 详情在下载前发送
        if show_info and not info_after:
            yield event.plain_result(self._render_message("message_info", variables))

        yield event.plain_result(self._render_message("message_start", variables))

        reporter = _ProgressReporter(event, self._progress_text)

        async with self._get_semaphore(config):
            result = await self._service.download(
                album_id,
                progress=reporter.report,
                force=force,
                cached=cached,
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

        # 服务侧会用实际下载数与接口详情修正信息，这里同步到模板变量
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

    def _progress_text(self, done: int, total: int) -> str:
        if total > 0:
            percent = min(100, int(done / total * 100))
            return self._render_message(
                "message_progress",
                {"percent": str(percent), "done": str(done), "total": str(total)},
            )

        return self._render_message("message_progress_count", {"done": str(done)})

    #  模板与变量

    def _render_message(self, key: str, variables: dict) -> str:
        # 从模块配置取模板渲染；缺失变量保留 {name} 占位符
        config = self._service.config or self.load_module_config()
        return render_template(config.get(key), variables)

    def _info_from_cached(self, album_id: int, cached: dict) -> AlbumInfo:
        # info.json 无效时至少从 PDF 文件名恢复标题，避免缓存命中还要联网
        pdf_name = str(cached.get("pdf_name") or "")
        prefix = f"JM{album_id}-"
        title = ""
        if (
            pdf_name.lower().startswith(prefix.lower())
            and pdf_name.lower().endswith(".pdf")
        ):
            title = pdf_name[len(prefix) : -len(".pdf")]
        return AlbumInfo(id=str(album_id), name=title or "未知")

    def _info_variables(self, album_id: int, info) -> dict:
        page_count = int(getattr(info, "page_count", 0) or 0)
        return {
            "id": str(album_id),
            "title": self._message_title(info),
            "author": str(getattr(info, "author", "") or "").strip() or "未知",
            "pages": str(page_count) if page_count > 0 else "未知",
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
                parse_int(defaults.get("jm_max_concurrent"), 2),
            ),
        )

        if self._semaphore is None or self._semaphore_limit != limit:
            self._semaphore = asyncio.Semaphore(limit)
            self._semaphore_limit = limit

        return self._semaphore


class _ProgressReporter:
    # 下载进度节流：按百分比/张数步长与最小时间间隔发送，失败后不再重试
    # 用 event.send 直接发送，避免把 MessageEventResult 塞回指令生成器

    _MIN_STEP = 10
    _MIN_INTERVAL = 2.0

    def __init__(self, event, render) -> None:
        self._event = event
        self._render = render
        self._last_percent = -1
        self._last_count = 0
        self._last_at = 0.0
        self._disabled = False
        self._lock = asyncio.Lock()

    async def report(self, done: int, total: int) -> None:
        if self._disabled or done <= 0:
            return

        loop = asyncio.get_running_loop()
        percent = self._due(done, total, loop.time())
        if percent is None:
            return

        async with self._lock:
            if self._disabled:
                return
            # 等锁期间可能已被其它回调推进
            now = loop.time()
            percent = self._due(done, total, now)
            if percent is None:
                return

            text = self._render(done, total)
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
            if total > 0:
                self._last_percent = percent
            else:
                self._last_count = done

    def _due(self, done: int, total: int, now: float) -> int | None:
        # 返回本次应发送的百分比；未知总数时返回 -1，None 表示不发送
        if total > 0:
            percent = min(100, int(done * 100 / total))
            final = percent >= 100 and self._last_percent < 100
            if percent < self._last_percent + self._MIN_STEP and not final:
                return None
            if now - self._last_at < self._MIN_INTERVAL and not final:
                return None
            return percent

        if done < self._last_count + self._MIN_STEP:
            return None
        if now - self._last_at < self._MIN_INTERVAL:
            return None
        return -1
