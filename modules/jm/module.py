"""JMComic 漫画下载模块

继承 ModuleBase，实现 JMComic 漫画的下载和 PDF 转换功能。

设计原则：
1. 模块自治：JM 模块管理自己的配置、下载逻辑
2. 统一接口：通过 ModuleBase 提供统一的接口供总管理模块调用
3. 模块隔离：JM 模块不直接访问其他模块，通过注册中心通信
"""

import asyncio
from pathlib import Path
from typing import Callable

from ...core.module import ModuleBase
from .downloader import JMDownloader
from .utils import normalize_album_id


class JMModule(ModuleBase):
    """JMComic 漫画下载模块

    继承 ModuleBase，实现 JMComic 漫画的下载和 PDF 转换功能。
    """

    def __init__(self, plugin_dir: Path, plugin_name: str):
        """初始化 JM 模块

        Args:
            plugin_dir: 插件目录路径
            plugin_name: 插件名称
        """
        super().__init__(plugin_dir, plugin_name)

        # 初始化下载管理器
        self._downloader = JMDownloader(self.get_config_path())

    @property
    def module_name(self) -> str:
        """模块名称"""
        return "jm"

    @property
    def module_icon(self) -> str:
        """模块图标"""
        return ""

    @property
    def module_desc(self) -> str:
        """模块描述"""
        return "JMComic 漫画下载"

    # ══════════════════════════════════════════
    #  查询接口（实现基类抽象方法）
    # ══════════════════════════════════════════

    async def query(self, account: dict) -> dict:
        """查询（下载）漫画

        Args:
            account: 包含漫画 ID 的配置

        Returns:
            查询结果字典
        """
        album_id = account.get("album_id")
        if not album_id:
            return {
                "success": False,
                "account_name": "JMComic",
                "error": "缺少漫画 ID"
            }

        try:
            # 检查本地缓存
            local_cache = self._downloader.check_local(str(album_id))
            if local_cache and local_cache.get("has_pdf"):
                return {
                    "success": True,
                    "account_name": f"JM{album_id}",
                    "data": {
                        "cached": True,
                        "pdf_path": local_cache.get("pdf_path"),
                        "pdf_name": local_cache.get("pdf_name"),
                        "pdf_size_mb": local_cache.get("pdf_size_mb", 0),
                    }
                }

            # 获取漫画信息
            album_info = await self._downloader.get_album_info(str(album_id))

            return {
                "success": True,
                "account_name": f"JM{album_id}",
                "data": {
                    "cached": False,
                    "name": album_info.get("name", "未知"),
                    "image_count": album_info.get("image_count", 0),
                }
            }
        except Exception as e:
            return {
                "success": False,
                "account_name": f"JM{album_id}",
                "error": str(e)
            }

    # ══════════════════════════════════════════
    #  下载功能
    # ══════════════════════════════════════════

    async def download(
        self,
        album_id: str | int,
        send_file: bool = True,
        progress_callback: Callable[[int, int, str], None] | None = None,
        force_redownload: bool = False,
    ) -> dict:
        """下载漫画并生成 PDF

        Args:
            album_id: 漫画 ID
            send_file: 是否返回文件路径用于发送
            progress_callback: 进度回调函数
            force_redownload: 是否强制重新下载

        Returns:
            包含下载结果的字典
        """
        return await self._downloader.download(
            album_id=str(album_id),
            send_file=send_file,
            progress_callback=progress_callback,
            force_redownload=force_redownload,
        )

    def check_local(self, album_id: str | int) -> dict | None:
        """检查本地是否有已下载的内容

        Args:
            album_id: 漫画 ID

        Returns:
            如果本地有内容，返回包含信息的字典，否则返回 None
        """
        return self._downloader.check_local(str(album_id))

    async def get_album_info(self, album_id: str | int) -> dict:
        """获取漫画信息

        Args:
            album_id: 漫画 ID

        Returns:
            漫画信息字典
        """
        info = await self._downloader.get_album_info(str(album_id))
        return info if isinstance(info, dict) else info.to_dict()

    def reload_config(self):
        """重新加载配置"""
        self._downloader.reload_config()

    # ══════════════════════════════════════════
    #  Web API 支持
    # ══════════════════════════════════════════

    def get_web_apis(self) -> list[dict]:
        """获取 JM 模块提供的 Web API 列表

        Returns:
            API 定义列表
        """
        return [
            {
                "path": "config",
                "handler": self._handle_get_config,
                "methods": ["GET"],
                "desc": "获取 JM 下载配置"
            },
            {
                "path": "config",
                "handler": self._handle_save_config,
                "methods": ["POST"],
                "desc": "保存 JM 下载配置"
            },
        ]

    async def _handle_get_config(self):
        """获取 JM 配置 API"""
        from astrbot.api.web import json_response

        config = self.load_config("config.json")

        # 合并默认配置
        default_config = {
            "jm_enabled": True,
            "jm_send_file": True,
            "jm_max_file_size": 10,
            "jm_cookies": "",
            "jm_proxy": "",
            "jm_timeout": 20,
            "jm_retry_times": 3,
            "jm_image_threads": 16,
            "jm_photo_threads": 4,
            "jm_max_concurrent": 1,
        }
        default_config.update(config)

        return json_response(default_config)

    async def _handle_save_config(self):
        """保存 JM 配置 API"""
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        if not payload:
            return error_response("缺少配置数据")

        # 读取现有配置并更新
        existing = self.load_config("config.json")
        existing.update(payload)

        # 保存配置
        if self.save_config(existing, "config.json"):
            # 重新加载下载器配置
            self.reload_config()
            return json_response({"status": "ok"})
        else:
            return error_response("保存失败")

    # ══════════════════════════════════════════
    #  指令支持
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        """获取 JM 模块提供的指令列表

        Returns:
            指令定义列表
        """
        return [
            {
                "name": "jm",
                "desc": "下载 JMComic 漫画 PDF：/jm <数字ID> [redownload]",
                "handler": "handle_jm_command"
            }
        ]

    async def handle_command(self, command: str, args: list[str], event) -> None:
        """处理 JM 指令

        Args:
            command: 指令名称
            args: 指令参数
            event: AstrBot 事件对象
        """
        if command == "jm":
            async for result in self._handle_jm_command(args, event):
                yield result

    async def _handle_jm_command(self, args: list[str], event):
        """处理 JM 指令的具体实现

        Args:
            args: 指令参数
            event: AstrBot 事件对象
        """
        from astrbot.api.message_components import File

        # 从配置读取
        jm_cfg = self.load_config("config.json")

        # 检查是否启用
        if not jm_cfg.get("jm_enabled", True):
            yield event.plain_result("JM 下载功能当前已关闭")
            return

        # 只允许私聊
        if event.get_group_id():
            yield event.plain_result("JM 下载仅支持私聊使用，请私聊发送命令")
            return

        # 解析参数
        if not args:
            yield event.plain_result(
                "用法：/jm <数字ID> [redownload]\n"
                "例如：/jm 123456\n"
                "添加 redownload 可强制重新下载"
            )
            return

        jm_id = args[0]
        option = args[1] if len(args) > 1 else ""

        # 解析 ID 和选项
        force_redownload = option.lower() == "redownload"
        album_id = normalize_album_id(jm_id)
        if album_id is None:
            yield event.plain_result(
                "无效的漫画 ID\n"
                "用法：/jm <数字ID> [redownload]"
            )
            return

        # 是否发送文件
        send_file = jm_cfg.get("jm_send_file", True)
        # 文件大小限制（MB），0 表示不限制
        max_file_size_mb = jm_cfg.get("jm_max_file_size", 10)

        # 获取漫画信息
        album_info = await self.get_album_info(album_id)

        # 构建简短信息
        info_parts = [f"JM{album_id}"]
        if isinstance(album_info, dict):
            if album_info.get('name') and album_info['name'] != '未知':
                info_parts.append(album_info['name'])
            if album_info.get('image_count'):
                info_parts.append(f"{album_info['image_count']}P")

        # 如果不强制重新下载，检查本地缓存
        if not force_redownload:
            local_cache = self.check_local(album_id)
            if local_cache and local_cache['has_pdf']:
                # 检查文件大小限制
                if send_file and local_cache.get("pdf_path"):
                    if max_file_size_mb > 0 and local_cache['pdf_size_mb'] > max_file_size_mb:
                        yield event.plain_result(f"{' | '.join(info_parts)}\n文件过大，跳过发送")
                    else:
                        yield event.chain_result([
                            File(name=local_cache["pdf_name"], file=local_cache["pdf_path"])
                        ])
                else:
                    yield event.plain_result(f"{' | '.join(info_parts)}\n本地已有缓存")
                return

        # 无缓存或强制重新下载
        yield event.plain_result(f"{' | '.join(info_parts)}\n正在下载...")

        # 进度消息追踪
        last_progress_msg = ""

        async def send_progress(current: int, total: int, msg: str):
            """发送或更新进度消息（只发送有进度的消息）"""
            nonlocal last_progress_msg

            # 只处理有进度值的消息
            if total <= 0 or current <= 0:
                return

            # 构建进度消息
            percent = int(current / total * 100)
            progress_msg = f"下载中 {percent}%"

            # 避免重复发送相同消息
            if progress_msg == last_progress_msg:
                return
            last_progress_msg = progress_msg

            try:
                await event.send(event.message_result().message(progress_msg))
            except Exception:
                pass

        # 进度回调函数
        def progress_callback(current: int, total: int, msg: str):
            """同步回调，转换为异步发送"""
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(send_progress(current, total, msg))
                else:
                    loop.run_until_complete(send_progress(current, total, msg))
            except Exception:
                pass

        # 执行下载
        result = await self.download(
            album_id,
            send_file=send_file,
            progress_callback=progress_callback,
            force_redownload=True,  # 已经检查过缓存，这里强制下载
        )

        if result.get("success"):
            # 发送文件
            if send_file and "pdf_path" in result:
                # 检查文件大小限制
                file_size_mb = result.get("file_size_mb", 0)
                if max_file_size_mb > 0 and file_size_mb > max_file_size_mb:
                    yield event.plain_result("文件过大，跳过发送")
                else:
                    try:
                        pdf_path = result["pdf_path"]
                        pdf_name = result["pdf_name"]

                        # 使用 chain_result 发送文件
                        yield event.chain_result([
                            File(name=pdf_name, file=pdf_path)
                        ])

                    except Exception as e:
                        yield event.plain_result(f"发送失败: {e}")
        else:
            yield event.plain_result(result.get("message", "下载失败"))
