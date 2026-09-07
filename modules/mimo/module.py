"""MiMo 平台模块

继承 ModuleBase，实现 MiMo 平台的账号管理和用量查询功能。

设计原则：
1. 模块自治：MiMo 模块管理自己的配置、账号、查询逻辑
2. 统一接口：通过 ModuleBase 提供统一的接口供总管理模块调用
3. 模块隔离：MiMo 模块不直接访问其他模块，通过注册中心通信
"""

import asyncio
from pathlib import Path

from ...core.module import ModuleBase
from .account import MiAccount
from .exceptions import LoginError, OtpRequired, PassTokenExpired, StsError
from .manager import MimoManager
from .query import is_auth_error, is_valid_response, query_mimo
from .result import MimoResult
from .utils import load_config, load_default_template


class MimoModule(ModuleBase):
    """MiMo 平台模块

    继承 ModuleBase，实现 MiMo 平台的账号管理和用量查询功能。
    """

    def __init__(self, plugin_dir: Path, plugin_name: str):
        """初始化 MiMo 模块

        Args:
            plugin_dir: 插件目录路径
            plugin_name: 插件名称
        """
        super().__init__(plugin_dir, plugin_name)

        # 加载配置
        self._config = load_config(plugin_dir)
        self._default_template = load_default_template(plugin_dir)

        # 创建内部管理器（处理登录等复杂逻辑）
        self._manager = MimoManager(plugin_dir)

    @property
    def module_name(self) -> str:
        """模块名称"""
        return "mimo"

    @property
    def module_icon(self) -> str:
        """模块图标"""
        return self._config.get("platform_icon", "📋")

    @property
    def module_desc(self) -> str:
        """模块描述"""
        return "小米 MiMo 平台用量查询"

    # ══════════════════════════════════════════
    #  账号管理（覆盖基类方法）
    # ══════════════════════════════════════════

    def get_accounts(self) -> list[dict]:
        """获取所有 MiMo 账号

        覆盖基类方法，添加 MiMo 特有的默认字段填充。

        Returns:
            账号配置列表
        """
        accounts = super().get_accounts()

        # 为缺少 device_id 和 ua 的账号填充默认值
        changed = False
        default_device_id = self._config.get("default_device_id", "wb_MIQUERY000001")
        default_ua = self._config.get("default_ua", "")

        for acc in accounts:
            if not acc.get("device_id"):
                acc["device_id"] = default_device_id
                changed = True
            if not acc.get("ua"):
                acc["ua"] = default_ua
                changed = True

        if changed:
            self.save_accounts(accounts)

        return accounts

    # ══════════════════════════════════════════
    #  查询接口（实现基类抽象方法）
    # ══════════════════════════════════════════

    async def query(self, account: dict) -> dict:
        """查询单个 MiMo 账号

        Args:
            account: 账号配置

        Returns:
            查询结果字典
        """
        label = account.get("name") or account.get("account") or "MiMo账号"
        template = self.get_account_template(account)

        try:
            result_data = await self._manager.query_one(account)

            if "error" in result_data:
                return {
                    "success": False,
                    "account_name": label,
                    "error": result_data["error"],
                    "template": template,
                }

            return {
                "success": True,
                "account_name": label,
                "data": result_data,
                "template": template,
            }
        except Exception as e:
            return {
                "success": False,
                "account_name": label,
                "error": str(e),
                "template": template,
            }

    # ══════════════════════════════════════════
    #  登录相关（委托给内部管理器）
    # ══════════════════════════════════════════

    async def ensure_account(self, acc: dict) -> dict:
        """确保账号有可用凭据

        Args:
            acc: 账号配置

        Returns:
            更新后的账号配置
        """
        return await self._manager.ensure_account(acc)

    async def re_login_account(self, acc: dict) -> dict:
        """重新登录账号

        Args:
            acc: 账号配置

        Returns:
            更新后的账号配置
        """
        return await self._manager.re_login_account(acc)

    def login_account(self, acc: dict, otp_code: str | None = None) -> dict:
        """执行登录

        Args:
            acc: 账号配置
            otp_code: OTP 验证码（可选）

        Returns:
            登录结果
        """
        return self._manager.login_account(acc, otp_code)

    def get_pending_otp_account(self) -> str | None:
        """获取等待 OTP 验证的账号名称

        Returns:
            账号名称，如果没有则返回 None
        """
        return self._manager.get_pending_otp_account()

    def submit_otp(self, otp_code: str) -> dict:
        """提交 OTP 验证码

        Args:
            otp_code: OTP 验证码

        Returns:
            登录结果
        """
        return self._manager.submit_otp(otp_code)

    # ══════════════════════════════════════════
    #  Web API 支持
    # ══════════════════════════════════════════

    def get_web_apis(self) -> list[dict]:
        """获取 MiMo 模块提供的 Web API 列表

        Returns:
            API 定义列表
        """
        return [
            {
                "path": "login",
                "handler": self._handle_login_api,
                "methods": ["POST"],
                "desc": "MiMo 登录"
            },
            {
                "path": "test",
                "handler": self._handle_test_api,
                "methods": ["POST"],
                "desc": "MiMo 测试查询"
            },
        ]

    async def _handle_login_api(self):
        """处理 MiMo 登录 API"""
        from ...common.utils import load_json_file, save_json_file
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        index = payload.get("index")
        account = payload.get("account", "").strip()
        password = payload.get("password", "").strip()
        otp_code = payload.get("otp_code", "").strip()

        if index is None:
            return error_response("缺少 index 参数")

        try:
            index = int(index)
        except (TypeError, ValueError):
            return error_response("index 必须是整数")

        # 获取账号列表
        accounts = self.get_accounts()

        if index < 0 or index >= len(accounts):
            return error_response("账号索引无效")

        acc = accounts[index]

        # 更新账号密码
        if account:
            acc["account"] = account
        if password:
            acc["password"] = password

        # 执行登录
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.login_account(acc, otp_code=otp_code if otp_code else None)
            )

            # 更新账号信息
            acc.update(result)
            accounts[index] = acc
            self.save_accounts(accounts)

            return json_response({
                "status": "ok",
                "message": "登录成功",
                "account": {
                    "userId": acc.get("userId", ""),
                    "serviceToken": acc.get("serviceToken", ""),
                    "passToken": acc.get("passToken", "")
                }
            })
        except Exception as e:
            error_name = type(e).__name__
            if error_name == "OtpRequired":
                return json_response({
                    "status": "otp_required",
                    "message": "验证码已发送，请输入验证码"
                })
            else:
                return json_response({
                    "status": "error",
                    "message": str(e)
                })

    async def _handle_test_api(self):
        """处理 MiMo 测试查询 API"""
        from astrbot.api.web import json_response, request
        from astrbot.api import logger

        payload = await request.json(default={})
        account = payload

        if not account:
            return json_response({
                "status": "error",
                "message": "缺少账号配置"
            })

        try:
            logger.info(f"[MiMo测试] 开始测试查询, 账号: {account.get('account', 'N/A')}")
            result = await self.query(account)

            if not result.get("success"):
                logger.warning(f"[MiMo测试] 查询返回错误: {result.get('error')}")
                return json_response({
                    "status": "error",
                    "message": result.get("error", "查询失败")
                })

            logger.info(f"[MiMo测试] 查询成功")
            return json_response({
                "status": "ok",
                "message": "测试成功",
                "credentials": {
                    "userId": account.get("userId", ""),
                    "passToken": account.get("passToken", ""),
                    "serviceToken": account.get("serviceToken", "")
                }
            })
        except Exception as e:
            logger.error(f"[MiMo测试] 异常: {type(e).__name__}: {e}")
            return json_response({
                "status": "error",
                "message": f"{type(e).__name__}: {e}"
            })

    # ══════════════════════════════════════════
    #  指令支持
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        """获取 MiMo 模块提供的指令列表

        Returns:
            指令定义列表
        """
        return [
            {
                "name": "mimo",
                "desc": "MiMo 查询指令",
                "handler": "handle_mimo_command"
            }
        ]

    async def handle_command(self, command: str, args: list[str], event) -> None:
        """处理 MiMo 指令

        Args:
            command: 指令名称
            args: 指令参数
            event: AstrBot 事件对象
        """
        if command == "mimo":
            async for result in self._handle_mimo_command(args, event):
                yield result

    async def _handle_mimo_command(self, args: list[str], event):
        """处理 MiMo 指令的具体实现

        Args:
            args: 指令参数
            event: AstrBot 事件对象
        """
        accounts = self.get_accounts()

        # /mimo otp <验证码> — 提交 OTP 验证码
        if args and args[0].lower() == "otp":
            if len(args) < 2:
                yield event.plain_result("用法: /mimo otp <验证码>")
                return

            otp_code = args[1].strip()
            if not otp_code:
                yield event.plain_result("验证码不能为空")
                return

            # 检查是否有等待 OTP 的账号
            pending = self.get_pending_otp_account()
            if not pending:
                yield event.plain_result("没有等待 OTP 验证的账号")
                return

            yield event.plain_result("正在提交验证码...")

            try:
                result = self.submit_otp(otp_code)

                # 更新账号信息
                for acc in accounts:
                    if acc.get("account") == pending or acc.get("name") == pending:
                        acc.update(result)
                        break
                self.save_accounts(accounts)

                yield event.plain_result(f"✅ OTP 验证成功！账号 {pending} 已登录")

                # 自动重新查询该账号
                target_acc = None
                for acc in accounts:
                    if acc.get("account") == pending or acc.get("name") == pending:
                        target_acc = acc
                        break

                if target_acc:
                    yield event.plain_result("🔍 正在查询...")
                    query_result = await self.query(target_acc)
                    if not query_result.get("success"):
                        yield event.plain_result(f"❌ {query_result.get('error')}")
                    else:
                        mr = MimoResult(
                            success=True,
                            account_name=pending,
                            data=query_result.get("data", {}),
                            template=query_result.get("template")
                        )
                        yield event.plain_result(mr.to_text())
            except Exception as e:
                yield event.plain_result(f"❌ OTP 验证失败: {e}")
            return

        # /mimo ls — 列出所有账号
        if args and args[0].lower() == "ls":
            if not accounts:
                yield event.plain_result("❌ 还没有配置 MiMo 账号\n请在网页管理界面添加账号")
                return
            lines = [f"📋 共 {len(accounts)} 个 MiMo 账号:"]
            for i, acc in enumerate(accounts):
                status = "✅" if acc.get("serviceToken") else "❌"
                name = acc.get("name") or acc.get("account") or f"MiMo账号{i+1}"
                lines.append(f"  {i + 1}. {status} {name}")
            yield event.plain_result("\n".join(lines))
            return

        # /mimo del <序号或名称> — 删除指定账号
        if args and args[0].lower() == "del":
            if len(args) < 2:
                yield event.plain_result("用法: /mimo del <序号或名称>")
                return

            del_arg = args[1]

            # 尝试按序号删除
            if del_arg.isdigit():
                del_idx = int(del_arg) - 1
                if 0 <= del_idx < len(accounts):
                    deleted = self.delete_account(del_idx)
                    if deleted:
                        name = deleted.get("name") or deleted.get("account") or "未知"
                        yield event.plain_result(f"✅ 已删除: {name}")
                    else:
                        yield event.plain_result("❌ 删除失败")
                    return

            # 按名称删除
            for i, acc in enumerate(accounts):
                name = acc.get("name") or acc.get("account") or ""
                if name == del_arg:
                    deleted = self.delete_account(i)
                    if deleted:
                        yield event.plain_result(f"✅ 已删除: {name}")
                    else:
                        yield event.plain_result("❌ 删除失败")
                    return

            yield event.plain_result(f"❌ 未找到账号: {del_arg}")
            return

        # /mimo — 查询所有账号
        if not args:
            if not accounts:
                yield event.plain_result("❌ 还没有配置 MiMo 账号\n请在网页管理界面添加账号")
                return
            yield event.plain_result("🔍 正在查询所有 MiMo 账号...")

            # 查询所有账号
            for acc in accounts:
                result = await self.query(acc)
                label = acc.get("name") or acc.get("account") or "MiMo账号"
                if not result.get("success"):
                    yield event.plain_result(f"📋 {label}\n❌ {result.get('error')}")
                else:
                    mr = MimoResult(
                        success=True,
                        account_name=label,
                        data=result.get("data", {}),
                        template=result.get("template")
                    )
                    yield event.plain_result(mr.to_text())
            return

        # /mimo <名称> — 查询指定账号
        query_arg = args[0]

        # 按名称查找
        for acc in accounts:
            name = acc.get("name") or acc.get("account") or ""
            if name == query_arg:
                yield event.plain_result("🔍 正在查询...")
                result = await self.query(acc)
                if not result.get("success"):
                    yield event.plain_result(f"📋 {name}\n❌ {result.get('error')}")
                else:
                    mr = MimoResult(
                        success=True,
                        account_name=name,
                        data=result.get("data", {}),
                        template=result.get("template")
                    )
                    yield event.plain_result(mr.to_text())
                return

        yield event.plain_result(f"❌ 未找到账号: {query_arg}\n使用 /mimo ls 查看所有账号")
