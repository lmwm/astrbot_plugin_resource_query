# MiMo 平台模块
#
# 继承 ModuleBase，实现小米 MiMo 的账号管理与用量查询。
# 登录、凭据刷新等底层逻辑由内部 MimoManager 负责。
#
# 配置分层：
#   - 默认值（只读）→ config.py
#   - 用户配置（Views 保存，只存值）→ config/mimo/config.json
#   - 账号级覆盖 → config/mimo/<账号>.json

from __future__ import annotations

from pathlib import Path

from ...common.module_log import module_logger
from ...core.module import ModuleBase
from .config import ACCOUNT_FIELDS, ACCOUNT_GROUPS, DEFAULT_TEMPLATE, VARIABLES
from .manager import MimoManager
from .result import MimoResult
from .utils import get_default_device_id, get_default_ua

logger = module_logger("mimo")

# 需要持久化的凭据字段
_CREDENTIAL_KEYS = ("userId", "passToken", "serviceToken")


class MimoModule(ModuleBase):
    # 小米 MiMo 用量查询模块

    #  默认配置（来自 config.py）

    account_fields = ACCOUNT_FIELDS
    account_groups = ACCOUNT_GROUPS
    variable_defaults = VARIABLES
    default_template = DEFAULT_TEMPLATE

    def __init__(self, plugin_dir: Path, plugin_name: str) -> None:
        # 初始化模块
        super().__init__(plugin_dir, plugin_name)
        self._manager = MimoManager(plugin_dir)

    #  元信息

    @property
    def module_name(self) -> str:
        # 模块标识
        return "mimo"

    @property
    def module_title(self) -> str:
        # 模块显示名
        return "MiMo 查询"

    @property
    def module_icon(self) -> str:
        # 模块图标
        return "▤"

    @property
    def module_desc(self) -> str:
        # 模块描述
        return "小米 MiMo 平台余额与用量查询"

    #  能力声明

    @property
    def supports_accounts(self) -> bool:
        # 支持多账号管理
        return True

    @property
    def supports_template(self) -> bool:
        # 支持消息模板
        return True

    @property
    def supports_query(self) -> bool:
        # 支持查询
        return True

    @property
    def supports_login(self) -> bool:
        # 支持在 Views 中登录（含 OTP）
        return True

    @property
    def supports_test(self) -> bool:
        # 支持在 Views 中测试凭据
        return True

    @property
    def account_file_prefix(self) -> str:
        # 账号文件名前缀
        return "mimo_"

    @property
    def account_label(self) -> str:
        return "MiMo 账号"

    #  账号管理

    def get_accounts(self) -> list[dict]:
        # 读取账号并补齐默认设备信息（仅内存，不落盘）
        accounts = super().get_accounts()
        default_device_id = get_default_device_id()
        default_ua = get_default_ua()

        for acc in accounts:
            if not acc.get("device_id"):
                acc["device_id"] = default_device_id
            if not acc.get("ua"):
                acc["ua"] = default_ua

        return accounts

    def save_accounts(self, accounts: list[dict]) -> bool:
        # 保存账号：空白的设备字段自动填充默认值
        defaults = {
            "device_id": get_default_device_id(),
            "ua": get_default_ua(),
        }
        normalized = []

        for acc in accounts:
            item = dict(acc)
            for key, value in defaults.items():
                if not str(item.get(key) or "").strip():
                    item[key] = value
            normalized.append(item)

        return super().save_accounts(normalized)

    def update_credentials(self, account: dict, credentials: dict) -> bool:
        # 把刷新后的凭据写回账号文件
        filename = str(account.get("_filename") or "").strip()
        if not filename:
            return False

        accounts = super().get_accounts()
        for acc in accounts:
            if acc.get("_filename") == filename:
                acc.update(credentials)
                return self.save_accounts(accounts)

        return False

    #  查询

    async def query(self, account: dict) -> MimoResult:
        # 查询单个 MiMo 账号；凭据被自动刷新时持久化
        label = self.account_display_name(account) or "MiMo账号"
        template = self.get_account_template(account)
        before = {key: account.get(key, "") for key in _CREDENTIAL_KEYS}

        try:
            data = await self._manager.query_one(account)
        except Exception as e:
            return MimoResult(
                success=False,
                account_name=label,
                error=f"{type(e).__name__}: {e}",
                template=template,
            )

        after = {key: account.get(key, "") for key in _CREDENTIAL_KEYS}
        if after != before:
            self.update_credentials(account, after)

        if "error" in data:
            return MimoResult(
                success=False,
                account_name=label,
                error=data["error"],
                template=template,
            )

        return MimoResult(
            success=True, account_name=label, data=data, template=template
        )

    #  指令

    def get_commands(self) -> list[dict]:
        # 本模块指令列表
        return [{"name": "mimo", "desc": "MiMo 用量查询：/mimo [ls|del|otp|账号]"}]

    async def handle_command(self, command: str, args: list[str], event):
        # 列表/删除/查询交给基类，这里只处理 MiMo 特有的 OTP 验证码
        if command != "mimo":
            return

        if args and args[0].lower() == "otp":
            async for r in self._cmd_otp(args, event):
                yield r
            return

        async for r in super().handle_command(command, args, event):
            yield r

    def describe_account(self, acc: dict, index: int) -> str:
        status = "√" if acc.get("serviceToken") else "×"
        name = self.account_display_name(acc) or f"MiMo账号{index}"
        return f"{status} {name}"

    async def _cmd_otp(self, args: list[str], event):
        # 提交 OTP 验证码，成功后自动查询一次
        if len(args) < 2 or not args[1].strip():
            yield event.plain_result("用法: /mimo otp <验证码>")
            return

        pending = self._manager.get_pending_otp_account()
        if not pending:
            yield event.plain_result("× 没有等待 OTP 验证的账号")
            return

        yield event.plain_result("正在提交验证码...")

        try:
            credentials = self._manager.submit_otp(args[1].strip())
        except Exception as e:
            yield event.plain_result(f"× OTP 验证失败: {e}")
            return

        account = self.find_account(pending)
        if account:
            self.update_credentials(account, credentials)

        yield event.plain_result(f"√ OTP 验证成功，账号 {pending} 已登录")

        # 凭据已刷新，需要重新读取账号后再查询
        target = self.find_account(pending)
        if target:
            yield event.plain_result("正在查询...")
            yield event.plain_result(self.render(await self.query(target)))

    #  Views 接口

    def get_web_apis(self) -> list[dict]:
        # 配置读写由基类提供，这里只追加登录与测试
        return super().get_web_apis() + [
            {
                "path": "login",
                "handler": self._api_login,
                "methods": ["POST"],
                "desc": "登录账号",
            },
            {
                "path": "test",
                "handler": self._api_test,
                "methods": ["POST"],
                "desc": "测试查询",
            },
        ]

    async def _api_login(self):
        # 登录指定账号（支持 OTP）
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        filename = str(payload.get("filename") or "").strip()
        account_id = str(payload.get("account") or "").strip()
        password = str(payload.get("password") or "").strip()
        otp_code = str(payload.get("otp_code") or "").strip()

        if not filename:
            return error_response("缺少 filename 参数")

        account = self.find_account(filename)
        if not account:
            return error_response("账号不存在")

        if account_id:
            account["account"] = account_id
        if password:
            account["password"] = password

        # 先落盘，确保账号/密码变更不会因登录失败而丢失
        self.save_accounts(
            self._with_updated_account(
                filename,
                {
                    "account": account.get("account", ""),
                    "password": account.get("password", ""),
                },
            )
        )

        try:
            credentials = await self._manager.login_account_async(
                account, otp_code or None
            )
        except Exception as e:
            if type(e).__name__ == "OtpRequired":
                return json_response(
                    {"status": "otp_required", "message": "验证码已发送，请输入验证码"}
                )
            return json_response({"status": "error", "message": str(e)})

        self.update_credentials(account, credentials)
        return json_response({"status": "ok", "message": "登录成功"})

    async def _api_test(self):
        # 测试查询（不落盘，仅验证凭据可用）
        from astrbot.api.web import json_response, request

        payload = await request.json(default={})
        if not isinstance(payload, dict) or not payload:
            return json_response({"status": "error", "message": "缺少账号配置"})

        try:
            result = await self.query(payload)
        except Exception as e:
            logger.error(f"[MiMo] 测试查询异常: {type(e).__name__}: {e}")
            return json_response(
                {"status": "error", "message": f"{type(e).__name__}: {e}"}
            )

        if not result.success:
            return json_response(
                {"status": "error", "message": result.error or "查询失败"}
            )

        return json_response({"status": "ok", "message": "测试成功"})

    def _with_updated_account(self, filename: str, updates: dict) -> list[dict]:
        # 返回把指定账号更新后的完整账号列表
        accounts = super().get_accounts()
        for acc in accounts:
            if acc.get("_filename") == filename:
                acc.update(updates)
                break
        return accounts
