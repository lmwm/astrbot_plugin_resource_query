# JMComic 漫画下载模块
#
# 只负责指令语义与消息编排：解析参数、控制发送顺序、按模块配置里的模板渲染消息。
# 目录、缓存、下载由 JMService 负责；服务只产出数据，不拼用户文案。
#
# 流程：收到指令 → 查询信息 → 发送信息 → 已下载则跳过 → 下载 → 完成。
#
# 限制：仅允许私聊使用。

from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path
from typing import ClassVar

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
from .models import AlbumInfo, DownloadProgress, JMError
from .service import JMService
from .utils import normalize_album_id, pick_display_name

logger = module_logger("jm")

# 指令提示：属于用法说明，不随模板变化
_PRIVATE_ONLY_TEXT = "JM 下载仅支持私聊使用，请私聊发送指令"
_USAGE_SHORT = "用法：/jm [-F] <漫画ID>；/jm LS 查看当前任务"
_USAGE_TEXT = (
    f"{_USAGE_SHORT}\n"
    "例如：/jm 123456、/jm -F 123456、/jm LS\n"
    "-F（不区分大小写）表示忽略已下载内容，全部重新下载\n"
    "LS（不区分大小写）列出当前下载任务与进度"
)
_INVALID_ID_TEXT = f"无效的漫画 ID\n{_USAGE_SHORT}"

# 相邻两条消息之间的固定间隔，避免一次请求的消息扎堆
_MESSAGE_INTERVAL = 1.0

# 已删除的配置项；旧 config.json 里可能还留着，加载时清掉
_REMOVED_CONFIG_KEYS = (
    "jm_download_dir",
    "jm_dir_rule",
    "jm_make_pdf",
    "jm_send_file",
    "jm_max_file_size",
    "jm_jpeg_quality",
    "jm_show_info",
    "jm_info_after_download",
    "message_progress",
    "message_progress_count",
    "message_start",
    "message_cached",
    "message_downloaded",
    "message_done",
    "message_too_large",
    "message_send_failed",
    "message_no_pdf",
)

# 6.29.0–6.31.1 的完整漫画信息默认模板；6.32.0 起自动迁移为简短格式
_LEGACY_FULL_INFO_TEMPLATE = (
    "📖 {title}\n"
    "🆔 JM{id}\n"
    "🔗 {url}\n"
    "✍️ 作者：{authors}\n"
    "📅 发布：{pub_date} · 更新：{update_date}\n"
    "📄 页数：{pages} · 章节：{chapters}\n"
    "👀 观看：{views} · ❤️ 点赞：{likes} · 💬 评论：{comments}\n"
    "🏷️ 标签：{tags}\n"
    "🎭 人物：{actors}\n"
    "📚 作品：{works}\n"
    "📝 简介：{description}\n"
    "📑 章节：\n"
    "{chapter_list}"
)

# 6.32.0 的三行简短模板；6.33.0 起迁移为分章页数格式
_LEGACY_SHORT_INFO_TEMPLATE = (
    "📖 {title}\n🆔 JM{id}\n📄 {pages} 页 · {chapters} 章"
)


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
            option_file=self.get_config_path() / "option.yaml",
        )
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_limit = 0
        # 正在进行的下载任务；供 /jm LS 查询，任务结束后移除
        self._tasks: list[dict] = []

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
        # 普通字段来自 config.json；下载参数从 option.yaml 读入并覆盖同名表单字段
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
        # 下载参数字段写 option.yaml，config.json 只存其余字段
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
            # 「模块设置」页：option 表单字段写回 option.yaml 默认值，其余字段从 config.json 删除
            defaults = self._config_store.default_values()
            self._config_store.remove_values(self._group_field_keys("option"))
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
        self._migrate_info_template()
        self._migrate_info_variables()
        self._service.bind_config(self.load_module_config())
        missing = dependencies.missing(self.required_packages)
        if missing:
            logger.error(
                f"缺少运行依赖：{'、'.join(missing)}；"
                f"未安装的模块：{'、'.join(dependencies.missing_modules(self.required_packages))}，"
                "/jm 只提示安装，不会下载"
            )

    def _migrate_option_location(self) -> None:
        # 6.16.x 的 option 在插件数据根；6.17.0 起与 config.json 同目录
        # 6.40 起扩展名改为 .yaml：旧 .yml 自动改名
        new = self._service.option_file
        candidates = (
            self.get_data_path() / "option.yaml",
            self.get_data_path() / "option.yml",
            self.get_config_path() / "option.yml",
        )
        for old in candidates:
            if old == new or not old.is_file():
                continue

            try:
                if not new.is_file():
                    new.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old), str(new))
                    logger.info(
                        f"已将 {old.name} 迁移到 {new.parent.name}/option.yaml"
                    )
                    continue
                # 新文件已存在：保留旧文件并提示，避免覆盖用户配置
                logger.warning(f"旧配置文件 {old} 仍存在，请手动确认后删除")
            except OSError as e:
                logger.warning(f"迁移 {old.name} 失败：{type(e).__name__}: {e}")

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
        # 旧版把下载参数存在 config.json；搬到 option.yaml 后删除旧键
        user_values = self._config_store.user_values()
        legacy = {
            key: value for key, value in user_values.items() if key in OPTION_FIELDS
        }
        if legacy:
            self._service.update_option_values(legacy)
            self._config_store.remove_values(list(legacy))
            logger.info(f"已将 {len(legacy)} 个下载参数迁移到 option.yaml")

        # 已删除的配置项；旧 config.json 里可能还留着，加载时清掉
        removed = [
            key
            for key in _REMOVED_CONFIG_KEYS
            if key in self._config_store.user_keys()
        ]
        if removed:
            self._config_store.remove_values(removed)
            logger.info(f"已清理过期的 JM 配置项：{'、'.join(removed)}")

    def _migrate_info_template(self) -> None:
        # 旧默认模板自动换成当前格式；用户自定义模板不改
        saved = self._config_store.user_values().get("message_info")
        if not isinstance(saved, str):
            return
        legacy_templates = (
            _LEGACY_FULL_INFO_TEMPLATE,
            _LEGACY_SHORT_INFO_TEMPLATE,
        )
        if saved.strip() not in {item.strip() for item in legacy_templates}:
            return
        self._config_store.save_values(
            {"message_info": CONFIG_FIELDS["message_info"]["default"]}
        )
        logger.info("已将旧的漫画信息模板迁移为逐章变量格式")

    def _migrate_info_variables(self) -> None:
        # 6.42.0 删除旧模板变量：把用户模板里的旧变量换成当前可用的
        saved = self._config_store.user_values().get("message_info")
        if not isinstance(saved, str):
            return

        replacements = (
            ("{chapter_pages}", "{chapter}"),
            ("{chapter_list}", "{chapter}"),
            ("{chapter_1}", "{chapter}"),
            ("{chapter_2}", ""),
            ("{chapter_3}", ""),
            ("{chapter_4}", ""),
            ("{chapter_5}", ""),
            ("{authors}", "{author}"),
            ("{pages}", ""),
            ("{chapters}", ""),
            ("{cover}", ""),
            # 半角连续空格会被聊天客户端折叠；统一换成全角空格（宽度等于一个汉字）
            ("ID   JM{id}", "ID　JM{id}"),
            ("ID  JM{id}", "ID　JM{id}"),
            ("ID JM{id}", "ID　JM{id}"),
            ("I D JM{id}", "ID　JM{id}"),
            # 汇总行缩进到章节内容下方（全角空格）
            ("\n     {chapter_summary}", "\n　　{chapter_summary}"),
            ("\n    {chapter_summary}", "\n　　{chapter_summary}"),
            ("\n{chapter_summary}", "\n　　{chapter_summary}"),
        )
        updated = saved
        for old, new in replacements:
            updated = updated.replace(old, new)
        if updated == saved:
            return

        self._config_store.save_values({"message_info": updated})
        logger.info("已更新漫画信息模板的旧变量、ID 与汇总行格式")

    #  指令

    def get_commands(self) -> list[dict]:
        return [
            {
                "name": "jm",
                "desc": "下载 JMComic 漫画：/jm [-F] <ID>；/jm LS 查看当前任务",
            }
        ]

    async def handle_command(self, command: str, args: list[str], event):
        if command != "jm":
            return

        if event.get_group_id():
            yield event.plain_result(_PRIVATE_ONLY_TEXT)
            return

        if not args:
            yield event.plain_result(_USAGE_TEXT)
            return

        if args[0].lower() == "ls":
            yield event.plain_result(self._format_tasks())
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

        # 逐条发送，条与条之间留 1 秒，避免消息扎堆
        sent = False
        async for r in self._download_and_send(album_id, event, force):
            if sent:
                await asyncio.sleep(_MESSAGE_INTERVAL)
            yield r
            sent = True

    @staticmethod
    def _split_force(args: list[str]) -> tuple[str, bool]:
        # -F（不区分大小写）写在 ID 前；返回（ID 文本, 是否强制全量重下）
        if args and args[0].lower() == "-f":
            return (args[1] if len(args) > 1 else ""), True
        return (args[0] if args else ""), False

    #  流程编排

    async def _download_and_send(self, album_id: int, event, force: bool):
        # 一次下载的完整流程；异常兜底成模板消息，并记录开始/结束分割线
        label = "强制重下" if force else "按需下载"
        log_separator(logger, f"JM 下载开始：ID {album_id}（{label}）")

        variables = {"id": str(album_id), "title": "未知"}
        task = {
            "id": album_id,
            "title": "未知",
            "force": force,
            "status": "准备中",
            "progress": None,
            "started": time.monotonic(),
        }
        self._tasks.append(task)

        try:
            # 第一件事：告诉用户指令已收到，后续查询与判定都在此之后
            yield event.plain_result(
                self._render_message("message_received", variables)
            )
            async for result in self._run_flow(
                album_id, event, force, variables, task
            ):
                yield result
        except JMError as e:
            logger.error(f"JM{album_id} 流程失败：{e}")
            yield event.plain_result(
                self._render_message("message_error", {**variables, "error": str(e)})
            )
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
            logger.error(f"JM{album_id} 下载过程异常：{error}")
            yield event.plain_result(
                self._render_message("message_error", {**variables, "error": error})
            )
        finally:
            try:
                self._tasks.remove(task)
            except ValueError:
                pass
            log_separator(logger, f"JM 下载结束：ID {album_id}")

    async def _run_flow(
        self,
        album_id: int,
        event,
        force: bool,
        variables: dict,
        task: dict,
    ):
        # 1 查询漫画信息：失败直接报错，不进入下载
        try:
            info = await self._service.get_album_info(album_id, force=force)
        except JMError as e:
            task["status"] = "查询失败"
            logger.warning(f"JM{album_id} 查询失败：{e}")
            yield event.plain_result(
                self._render_message(
                    "message_error", {**variables, "error": str(e)}
                )
            )
            return
        # 章节 ID 会被 jmcomic 重定向到所属本子；后续判定、下载与目录统一用实际本子 ID
        if str(info.id).isdigit() and int(info.id) != album_id:
            album_id = int(info.id)
        task["id"] = album_id
        task["title"] = self._message_title(info)

        # 2 已下载判定：漫画信息里每章行尾显示【√】或【×】
        downloaded = not force and self._service.is_downloaded(
            str(album_id), info.page_count
        )
        task["status"] = "已下载" if downloaded else "待下载"
        variables.update(
            self._info_variables(album_id, info, all_downloaded=downloaded)
        )

        # 3 发送漫画信息（下载前后共用这一条）；已下载时这条就是最后一条
        yield event.plain_result(self._render_message("message_info", variables))
        if downloaded:
            return

        # 4 下载；进度只写任务表，供 /jm LS 查询
        async def record(progress: DownloadProgress) -> None:
            task["progress"] = progress

        config = self._service.config or self.load_module_config()
        task["status"] = "等待下载槽"
        async with self._get_semaphore(config):
            task["status"] = "下载中"
            result = await self._service.download(
                album_id,
                progress=record,
                force=force,
                info=info,
            )
        task["status"] = "收尾中"

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
            variables.update(
                self._info_variables(
                    album_id, result.album_info, all_downloaded=True
                )
            )

        # 5 完成：复用同一条漫画信息，章节行尾变为【√】
        yield event.plain_result(self._render_message("message_info", variables))

    #  任务查询（/jm LS）

    def _format_tasks(self) -> str:
        if not self._tasks:
            return "当前没有下载任务"
        lines = [f"当前下载任务（{len(self._tasks)}）："]
        now = time.monotonic()
        for index, task in enumerate(self._tasks, start=1):
            title = str(task.get("title") or "未知")
            force = "（强制重下）" if task.get("force") else ""
            progress = task.get("progress")
            if progress is None:
                detail = str(task.get("status") or "准备中")
            else:
                detail = self._task_progress_text(progress)
                if task.get("status") == "收尾中":
                    detail += "（收尾中）"
            elapsed = max(0, int(now - float(task.get("started") or now)))
            time_text = (
                f"{elapsed // 60} 分 {elapsed % 60} 秒"
                if elapsed >= 60
                else f"{elapsed} 秒"
            )
            lines.append(
                f"{index}. JM{task.get('id')} {title}{force} — {detail}"
                f"（{time_text}）"
            )
        return "\n".join(lines)

    @staticmethod
    def _task_progress_text(progress: DownloadProgress) -> str:
        if progress.chapter_index > 0 and progress.chapters_total > 0:
            chapter = f"第 {progress.chapter_index}/{progress.chapters_total} 章"
        else:
            chapter = "章节未知"
        if progress.chapter_pages_total > 0:
            return (
                f"{chapter} · 页 {progress.chapter_pages_done}/"
                f"{progress.chapter_pages_total}"
            )
        return f"{chapter} · 已下载 {progress.chapter_pages_done} 页"

    #  模板与变量

    def _render_message(self, key: str, variables: dict) -> str:
        # 从模块配置取模板渲染；{chapter} 每出现一次取下一章，写几个就显示几章
        config = self._service.config or self.load_module_config()
        template = str(config.get(key) or "")

        slot_count = template.count("{chapter}")
        for index in range(slot_count):
            template = template.replace(
                "{chapter}", f"{{chapter_{index + 1}}}", 1
            )

        render_vars = dict(variables)
        chapter_lines = render_vars.pop("chapter", [])
        if not isinstance(chapter_lines, (list, tuple)):
            chapter_lines = [str(chapter_lines)] if chapter_lines else []
        for index in range(slot_count):
            render_vars[f"chapter_{index + 1}"] = (
                str(chapter_lines[index]) if index < len(chapter_lines) else ""
            )

        # 超出实际章节数的槽位：整行删除，避免消息里留下空行
        empty_slots = {
            str(index + 1)
            for index in range(slot_count)
            if index >= len(chapter_lines)
        }
        if empty_slots:
            kept_lines: list[str] = []
            for line in template.split("\n"):
                slots = re.findall(r"\{chapter_(\d+)\}", line)
                if slots and all(slot in empty_slots for slot in slots):
                    continue
                kept_lines.append(line)
            template = "\n".join(kept_lines)

        return render_template(template, render_vars)

    def _info_variables(
        self,
        album_id: int,
        info: AlbumInfo,
        all_downloaded: bool = False,
    ) -> dict:
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

        chapter_items = [
            chapter for chapter in (info.chapters or []) if isinstance(chapter, dict)
        ]
        # 单章节本子的 pname 往往等于完整本子标题，消息里改用简短名（oname 优先），
        # 与下载目录名保持一致；多章节仍用每章自己的标题
        single_chapter = len(chapter_items) == 1
        brief_title = self._message_title(info)
        # 所有章节合并到 {chapter}：有几章就输出几行，不写死前 5 章
        chapter_lines: list[str] = []
        for chapter in chapter_items:
            index = str(chapter.get("index") or "").strip()
            pages = int(chapter.get("pages", 0) or 0)
            # 页数固定 3 位，不足补 0（第001章 - 010页）
            page_text = f"{pages:03d}页" if pages > 0 else "页数未知"
            flag = all_downloaded or chapter.get("downloaded") is True
            mark = "√" if flag else "×"
            name = str(chapter.get("name") or "").strip()
            if single_chapter:
                name = brief_title
            title = f" {name}" if name else ""
            # [√]/[×] 紧贴章节文字：宽度与 ID+全角空格、汇总两全角空格一致
            chapter_lines.append(
                f"[{mark}]第{index}章 - {page_text}{title}"
            )

        total_pages = f"{info.page_count:03d}" if info.page_count > 0 else "未知"
        return {
            "id": str(info.id or album_id),
            "title": self._message_title(info),
            "author": info.author.strip() or "未知",
            "chapter": chapter_lines,
            "chapter_summary": f"共 {info.chapter_count} 章 · {total_pages} 页",
            "url": text(info.url),
            "pub_date": date_text(info.pub_date),
            "update_date": date_text(info.update_date),
            "views": text(info.views),
            "likes": text(info.likes),
            "comments": str(info.comments),
            "tags": join_list(info.tags),
            "actors": join_list(info.actors),
            "works": join_list(info.works),
            "description": text(info.description, "无"),
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
