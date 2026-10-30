# MiMo 平台模块
#
# 继承 ModuleBase，实现小米 MiMo 的账号管理与用量查询。
# 登录、凭据刷新等底层逻辑由内部 MimoManager 负责。
#
# 配置分层：
#   - 模块级默认值（Views「模块设置」）→ config/mimo/config.json
#   - 只读兜底默认值 → modules/mimo/config.yaml
#   - 账号级覆盖 → config/mimo/<账号>.json

from __future__ import annotations

from pathlib import Path

from ...core.module import ModuleBase
from .manager import MimoManager
from .result import MimoResult
from .utils import get_default_device_id, get_default_template, get_default_ua
from .utils import get_var_definitions as _load_var_definitions

# 账号字段分组：三种凭据方式作为标签页，设备信息作为内联区块
_ACCOUNT_GROUPS = [
    {
        "key": "password",
        "label": "账号密码登录",
        "mode": "tab",
        "hint": "输入小米账号与密码，首次登录可能需要短信验证码",
    },
    {
        "key": "passtoken",
        "label": "PassToken",
        "mode": "tab",
        "hint": "已有 PassToken 时使用，插件会自动换取 ServiceToken",
    },
    {
        "key": "servicetoken",
        "label": "ServiceToken",
        "mode": "tab",
        "hint": "直接使用 ServiceToken 查询，无需再次登录",
    },
    {
        "key": "device",
        "label": "设备信息（可选）",
        "mode": "inline",
        "hint": "留空时保存会自动填充插件默认值，可点字段右侧的「↺」单独恢复默认",
    },
]

# 账号表单字段；group 决定字段出现在哪个分组
_ACCOUNT_FIELDS = [
    {"key": "name", "label": "账号名称", "type": "text", "hint": "留空则显示小米账号"},
    {
        "key": "account",
        "label": "小米账号",
        "type": "text",
        "group": "password",
        "hint": "手机号或邮箱",
    },
    {"key": "password", "label": "密码", "type": "password", "group": "password"},
    {
        "key": "userId",
        "label": "User ID",
        "type": "text",
        "group": ["passtoken", "servicetoken"],
        "hint": "登录后自动填充",
    },
    {
        "key": "passToken",
        "label": "PassToken",
        "type": "password",
        "group": "passtoken",
        "hint": "登录后自动填充",
    },
    {
        "key": "serviceToken",
        "label": "ServiceToken",
        "type": "password",
        "group": "servicetoken",
        "hint": "登录后自动填充",
    },
    {"key": "device_id", "label": "设备标识", "type": "text", "group": "device"},
    {"key": "ua", "label": "User-Agent", "type": "text", "group": "device"},
]

# 需要持久化的凭据字段
_CREDENTIAL_KEYS = ("userId", "passToken", "serviceToken")


class MimoModule(ModuleBase):
    # 小米 MiMo 用量查询模块

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

    #  字段定义

    def get_account_groups(self) -> list[dict]:
        # 账号字段分组定义
        return _ACCOUNT_GROUPS

    def get_account_fields(self) -> list[dict]:
        # 账号表单字段定义
        fields = [dict(field) for field in _ACCOUNT_FIELDS]
        defaults = {
            "device_id": get_default_device_id(),
            "ua": get_default_ua(),
        }

        for field in fields:
            if field["key"] in defaults:
                field["default"] = defaults[field["key"]]

        return fields

    def get_var_definitions(self) -> dict[str, str]:
        # 模板变量说明（来自 modules/mimo/config.yaml）
        return _load_var_definitions()

    def get_default_template(self) -> str:
        # 默认消息模板
        return get_default_template()

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
        from astrbot.api import logger
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
