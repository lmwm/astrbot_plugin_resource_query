"""MiMo 平台模块

继承 ModuleBase，实现小米 MiMo 的账号管理与用量查询。
登录、凭据刷新等底层逻辑由内部 MimoManager 负责。

配置分层：
  - 模块级默认值（Pages「模块设置」）→ config/mimo/config.json
  - 只读兜底默认值 → modules/mimo/config.yaml
  - 账号级覆盖 → config/mimo/<账号>.json
"""

from __future__ import annotations

from pathlib import Path

from ...core.module import ModuleBase
from .manager import MimoManager
from .result import MimoResult
from .utils import get_default_device_id, get_default_template, get_default_ua

# 模板变量说明（Pages 变量面板展示用）
_VAR_DEFINITIONS = {
    "label": "账号名称",
    "balance": "余额",
    "gift_balance": "赠送余额",
    "input_token": "输入 Token",
    "output_token": "输出 Token",
    "cache_token": "缓存 Token",
    "monthly_cost": "本月费用",
    "total_cost": "累计费用",
    "tpm": "TPM 限额",
    "rpm": "RPM 限额",
    "concurrency": "并发限额",
}

# 账号表单字段（Pages 通用渲染）
_ACCOUNT_FIELDS = [
    {"key": "name", "label": "账号名称", "type": "text", "hint": "留空则显示小米账号"},
    {"key": "account", "label": "小米账号", "type": "text", "hint": "手机号或邮箱"},
    {"key": "password", "label": "密码", "type": "password"},
    {"key": "device_id", "label": "设备标识", "type": "text", "hint": "留空使用模块默认值"},
    {"key": "ua", "label": "User-Agent", "type": "text", "hint": "留空使用模块默认值"},
    {"key": "userId", "label": "User ID", "type": "text", "hint": "登录后自动填充"},
    {"key": "passToken", "label": "PassToken", "type": "password", "hint": "登录后自动填充"},
    {"key": "serviceToken", "label": "ServiceToken", "type": "password", "hint": "登录后自动填充"},
]

# 需要持久化的凭据字段
_CREDENTIAL_KEYS = ("userId", "passToken", "serviceToken")


class MimoModule(ModuleBase):
    """小米 MiMo 用量查询模块"""

    def __init__(self, plugin_dir: Path, plugin_name: str) -> None:
        """初始化模块

        Args:
            plugin_dir: 插件目录路径。
            plugin_name: 插件名称。
        """
        super().__init__(plugin_dir, plugin_name)
        self._manager = MimoManager(plugin_dir)

    # ══════════════════════════════════════════
    #  元信息
    # ══════════════════════════════════════════

    @property
    def module_name(self) -> str:
        """模块标识"""
        return "mimo"

    @property
    def module_title(self) -> str:
        """模块显示名"""
        return "MiMo 查询"

    @property
    def module_icon(self) -> str:
        """模块图标"""
        return "📊"

    @property
    def module_desc(self) -> str:
        """模块描述"""
        return "小米 MiMo 平台余额与用量查询"

    # ══════════════════════════════════════════
    #  能力声明
    # ══════════════════════════════════════════

    @property
    def supports_accounts(self) -> bool:
        """支持多账号管理"""
        return True

    @property
    def supports_template(self) -> bool:
        """支持消息模板"""
        return True

    @property
    def supports_query(self) -> bool:
        """支持查询"""
        return True

    @property
    def supports_login(self) -> bool:
        """支持在 Pages 中登录（含 OTP）"""
        return True

    @property
    def supports_test(self) -> bool:
        """支持在 Pages 中测试凭据"""
        return True

    @property
    def account_file_prefix(self) -> str:
        """账号文件名前缀"""
        return "mimo_"

    # ══════════════════════════════════════════
    #  模块配置
    # ══════════════════════════════════════════

    def get_default_config(self) -> dict:
        """模块默认配置

        Returns:
            默认设备标识与 User-Agent。
        """
        return {
            "default_device_id": get_default_device_id(),
            "default_ua": get_default_ua(),
        }

    def get_config_fields(self) -> list[dict]:
        """模块配置字段定义

        Returns:
            字段列表。
        """
        return [
            {
                "key": "default_device_id",
                "label": "默认设备标识",
                "type": "text",
                "hint": "账号未单独配置时使用",
            },
            {
                "key": "default_ua",
                "label": "默认 User-Agent",
                "type": "text",
                "hint": "登录与查询共用，留空则使用配置文件内置值",
            },
        ]

    # ══════════════════════════════════════════
    #  字段定义
    # ══════════════════════════════════════════

    def get_account_fields(self) -> list[dict]:
        """账号表单字段定义

        Returns:
            字段列表。
        """
        return _ACCOUNT_FIELDS

    def get_var_definitions(self) -> dict[str, str]:
        """模板变量说明

        Returns:
            变量名到中文描述的映射。
        """
        return _VAR_DEFINITIONS

    def get_default_template(self) -> str:
        """默认消息模板

        Returns:
            来自 config.yaml 的默认模板。
        """
        return get_default_template()

    # ══════════════════════════════════════════
    #  账号管理
    # ══════════════════════════════════════════

    def get_accounts(self) -> list[dict]:
        """读取账号并补齐默认设备信息（仅内存，不落盘）

        Returns:
            账号配置列表。
        """
        accounts = super().get_accounts()
        config = self.load_module_config()
        default_device_id = config.get("default_device_id") or get_default_device_id()
        default_ua = config.get("default_ua") or get_default_ua()

        for acc in accounts:
            if not acc.get("device_id"):
                acc["device_id"] = default_device_id
            if not acc.get("ua"):
                acc["ua"] = default_ua

        return accounts

    def update_credentials(self, account: dict, credentials: dict) -> bool:
        """把刷新后的凭据写回账号文件

        Args:
            account: 账号配置（需带 _filename）。
            credentials: 要更新的字段。

        Returns:
            是否更新成功。
        """
        filename = str(account.get("_filename") or "").strip()
        if not filename:
            return False

        accounts = super().get_accounts()
        for acc in accounts:
            if acc.get("_filename") == filename:
                acc.update(credentials)
                return self.save_accounts(accounts)

        return False

    def _find_account(self, accounts: list[dict], identifier: str) -> dict | None:
        """按名称、账号或文件名查找账号

        Args:
            accounts: 账号列表。
            identifier: 账号名称、小米账号或文件名。

        Returns:
            匹配到的账号；未找到返回 None。
        """
        for acc in accounts:
            if identifier in (
                acc.get("name", ""),
                acc.get("account", ""),
                acc.get("_filename", ""),
            ):
                return acc
        return None

    # ══════════════════════════════════════════
    #  查询
    # ══════════════════════════════════════════

    async def query(self, account: dict) -> dict:
        """查询单个 MiMo 账号

        Args:
            account: 账号配置。

        Returns:
            统一结果字典。
        """
        label = account.get("name") or account.get("account") or "MiMo账号"
        template = self.get_account_template(account)
        before = {key: account.get(key, "") for key in _CREDENTIAL_KEYS}

        try:
            data = await self._manager.query_one(account)
        except Exception as e:
            return {
                "success": False,
                "account_name": label,
                "error": f"{type(e).__name__}: {e}",
                "template": template,
            }

        # 凭据被自动刷新时持久化，避免下次重复登录
        after = {key: account.get(key, "") for key in _CREDENTIAL_KEYS}
        if after != before:
            self.update_credentials(account, after)

        if "error" in data:
            return {
                "success": False,
                "account_name": label,
                "error": data["error"],
                "template": template,
            }

        return {
            "success": True,
            "account_name": label,
            "data": data,
            "template": template,
        }

    def get_result_class(self):
        """本模块使用的查询结果类

        Returns:
            MimoResult 类。
        """
        return MimoResult

    # ══════════════════════════════════════════
    #  指令
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        """本模块指令列表

        Returns:
            指令定义列表。
        """
        return [{"name": "mimo", "desc": "MiMo 用量查询：/mimo [ls|del|otp|账号]"}]

    async def handle_command(self, command: str, args: list[str], event):
        """处理 /mimo 指令

        Args:
            command: 指令名称。
            args: 参数列表。
            event: 消息事件。

        Yields:
            消息结果。
        """
        if command != "mimo":
            return

        accounts = self.get_accounts()

        if args and args[0].lower() == "ls":
            async for r in self._cmd_list(event, accounts):
                yield r
            return

        if args and args[0].lower() == "del":
            async for r in self._cmd_delete(args, event, accounts):
                yield r
            return

        if args and args[0].lower() == "otp":
            async for r in self._cmd_otp(args, event, accounts):
                yield r
            return

        if not args:
            async for r in self._cmd_query_all(event, accounts):
                yield r
            return

        async for r in self._cmd_query_one(args[0], event, accounts):
            yield r

    async def _cmd_list(self, event, accounts: list[dict]):
        """列出全部账号"""
        if not accounts:
            yield event.plain_result("❌ 还没有配置 MiMo 账号\n请在网页管理界面添加账号")
            return

        lines = [f"共 {len(accounts)} 个 MiMo 账号:"]
        for i, acc in enumerate(accounts, start=1):
            status = "✅" if acc.get("serviceToken") else "❌"
            name = acc.get("name") or acc.get("account") or f"MiMo账号{i}"
            lines.append(f"  {i}. {status} {name}")

        yield event.plain_result("\n".join(lines))

    async def _cmd_delete(self, args: list[str], event, accounts: list[dict]):
        """删除指定账号"""
        if len(args) < 2:
            yield event.plain_result("用法: /mimo del <序号或名称>")
            return

        target = args[1]
        account: dict | None = None

        if target.isdigit():
            index = int(target) - 1
            if 0 <= index < len(accounts):
                account = accounts[index]
        else:
            account = self._find_account(accounts, target)

        if not account:
            yield event.plain_result(f"❌ 未找到账号: {target}")
            return

        deleted = self.delete_account(str(account.get("_filename", "")))
        if not deleted:
            yield event.plain_result("❌ 删除失败")
            return

        name = deleted.get("name") or deleted.get("account") or target
        yield event.plain_result(f"✅ 已删除: {name}")

    async def _cmd_otp(self, args: list[str], event, accounts: list[dict]):
        """提交 OTP 验证码"""
        if len(args) < 2 or not args[1].strip():
            yield event.plain_result("用法: /mimo otp <验证码>")
            return

        pending = self._manager.get_pending_otp_account()
        if not pending:
            yield event.plain_result("❌ 没有等待 OTP 验证的账号")
            return

        yield event.plain_result("正在提交验证码...")

        try:
            credentials = self._manager.submit_otp(args[1].strip())
        except Exception as e:
            yield event.plain_result(f"❌ OTP 验证失败: {e}")
            return

        account = self._find_account(accounts, pending)
        if account:
            self.update_credentials(account, credentials)

        yield event.plain_result(f"✅ OTP 验证成功，账号 {pending} 已登录")

        # 登录成功后自动查询一次
        target = self._find_account(self.get_accounts(), pending)
        if target:
            yield event.plain_result("🔍 正在查询...")
            yield event.plain_result(self.render(await self.query(target)))

    async def _cmd_query_all(self, event, accounts: list[dict]):
        """查询全部账号"""
        if not accounts:
            yield event.plain_result("❌ 还没有配置 MiMo 账号\n请在网页管理界面添加账号")
            return

        yield event.plain_result("🔍 正在查询所有 MiMo 账号...")

        for acc in accounts:
            yield event.plain_result(self.render(await self.query(acc)))

    async def _cmd_query_one(self, identifier: str, event, accounts: list[dict]):
        """查询指定账号"""
        account = self._find_account(accounts, identifier)
        if not account:
            yield event.plain_result(f"❌ 未找到账号: {identifier}\n使用 /mimo ls 查看所有账号")
            return

        yield event.plain_result("🔍 正在查询...")
        yield event.plain_result(self.render(await self.query(account)))

    # ══════════════════════════════════════════
    #  Pages 接口
    # ══════════════════════════════════════════

    def get_web_apis(self) -> list[dict]:
        """本模块的 Pages 接口

        Returns:
            接口定义列表。
        """
        return [
            {"path": "config", "handler": self._api_get_config, "methods": ["GET"], "desc": "获取模块配置"},
            {"path": "config", "handler": self._api_save_config, "methods": ["POST"], "desc": "保存模块配置"},
            {"path": "login", "handler": self._api_login, "methods": ["POST"], "desc": "登录账号"},
            {"path": "test", "handler": self._api_test, "methods": ["POST"], "desc": "测试查询"},
        ]

    async def _api_get_config(self):
        """获取模块配置"""
        from astrbot.api.web import json_response

        return json_response(self.load_module_config())

    async def _api_save_config(self):
        """保存模块配置"""
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        if not isinstance(payload, dict) or not payload:
            return error_response("缺少配置数据")

        config = self.load_module_config()
        config.update(payload)
        if not self.save_module_config(config):
            return error_response("保存失败")

        return json_response({"status": "ok"})

    async def _api_login(self):
        """登录指定账号（支持 OTP）"""
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        filename = str(payload.get("filename") or "").strip()
        account_id = str(payload.get("account") or "").strip()
        password = str(payload.get("password") or "").strip()
        otp_code = str(payload.get("otp_code") or "").strip()

        if not filename:
            return error_response("缺少 filename 参数")

        account = self._find_account(self.get_accounts(), filename)
        if not account:
            return error_response("账号不存在")

        if account_id:
            account["account"] = account_id
        if password:
            account["password"] = password

        # 先落盘，确保账号/密码变更不会因登录失败而丢失
        self.save_accounts(self._with_updated_account(filename, {
            "account": account.get("account", ""),
            "password": account.get("password", ""),
        }))

        try:
            credentials = await self._manager.login_account_async(account, otp_code or None)
        except Exception as e:
            if type(e).__name__ == "OtpRequired":
                return json_response({"status": "otp_required", "message": "验证码已发送，请输入验证码"})
            return json_response({"status": "error", "message": str(e)})

        self.update_credentials(account, credentials)
        return json_response({"status": "ok", "message": "登录成功"})

    async def _api_test(self):
        """测试查询（不落盘，仅验证凭据可用）"""
        from astrbot.api import logger
        from astrbot.api.web import json_response, request

        payload = await request.json(default={})
        if not isinstance(payload, dict) or not payload:
            return json_response({"status": "error", "message": "缺少账号配置"})

        try:
            result = await self.query(payload)
        except Exception as e:
            logger.error(f"[MiMo] 测试查询异常: {type(e).__name__}: {e}")
            return json_response({"status": "error", "message": f"{type(e).__name__}: {e}"})

        if not result.get("success"):
            return json_response({"status": "error", "message": result.get("error", "查询失败")})

        return json_response({"status": "ok", "message": "测试成功"})

    def _with_updated_account(self, filename: str, updates: dict) -> list[dict]:
        """返回把指定账号更新后的完整账号列表

        Args:
            filename: 目标账号文件名。
            updates: 要更新的字段。

        Returns:
            更新后的账号列表。
        """
        accounts = super().get_accounts()
        for acc in accounts:
            if acc.get("_filename") == filename:
                acc.update(updates)
                break
        return accounts
