"""MiMo 平台管理器 - 统一管理登录、查询等功能"""

import asyncio
from pathlib import Path

from ..base import BasePlatform
from .account import MiAccount
from .exceptions import LoginError, OtpRequired, PassTokenExpired, StsError
from .query import is_auth_error, is_valid_response, query_mimo
from .result import MimoResult
from .utils import load_config, load_default_template


class MimoManager(BasePlatform):
    """MiMo 平台管理器"""

    def __init__(self, plugin_dir: Path):
        self._plugin_dir = plugin_dir
        self._config = load_config(plugin_dir)
        self._default_template = load_default_template(plugin_dir)
        # 缓存 MiAccount 实例，用于保持 OTP 会话状态
        self._mi_account_cache: dict[str, MiAccount] = {}

    @property
    def platform_name(self) -> str:
        return self._config.get("platform_name", "MiMo")

    @property
    def platform_icon(self) -> str:
        return self._config.get("platform_icon", "📋")

    # ══════════════════════════════════════════
    #  登录相关
    # ══════════════════════════════════════════

    async def ensure_account(self, acc: dict) -> dict:
        """异步：确保账号有可用凭据"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_ensure_account, acc)

    async def re_login_account(self, acc: dict) -> dict:
        """异步：查询失败后重新登录"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_re_login_account, acc)

    def login_account(self, acc: dict, otp_code: str | None = None) -> dict:
        """同步：完整登录流程（在线程中调用）"""
        return self._sync_login_account(acc, otp_code)

    def _create_mi_account(self, acc: dict) -> MiAccount:
        """创建或获取缓存的 MiAccount 实例
        
        使用 account + device_id 作为缓存 key，保持 OTP 会话状态
        """
        account = acc.get("account", "")
        device_id = acc.get("device_id", "")
        cache_key = f"{account}:{device_id}"
        
        # 如果有缓存的实例且正在OTP验证中，返回缓存
        if cache_key in self._mi_account_cache:
            cached = self._mi_account_cache[cache_key]
            if cached._otp_session is not None:
                return cached
        
        # 创建新实例并缓存
        mi = MiAccount(
            device_id=device_id,
            ua=acc.get("ua", ""),
            account_base=self._config.get("api", {}).get("account_base"),
        )
        self._mi_account_cache[cache_key] = mi
        return mi

    def _sync_ensure_account(self, acc: dict) -> dict:
        """同步：确保账号有可用凭据。优先级：serviceToken > passToken > account+password"""
        service_token = acc.get("serviceToken", "")
        pass_token = acc.get("passToken", "")
        user_id = acc.get("userId", "")

        if service_token and user_id:
            return acc

        if pass_token:
            mi = self._create_mi_account(acc)
            try:
                user_id, service_token = mi.login_with_passtoken(user_id, pass_token)
                acc["userId"] = user_id
                acc["serviceToken"] = service_token
                return acc
            except PassTokenExpired:
                acc["passToken"] = ""
            except (OSError, StsError):
                pass

        account = acc.get("account", "")
        password = acc.get("password", "")
        if account and password:
            mi = self._create_mi_account(acc)
            try:
                result = mi.login_with_password(account, password)
                acc["userId"] = result["userId"]
                acc["passToken"] = result["passToken"]
                acc["serviceToken"] = result["serviceToken"]
                return acc
            except OtpRequired:
                acc["_otp_required"] = True
            except LoginError as e:
                acc["_login_error"] = f"登录失败: {e}"
            except (OSError, StsError) as e:
                acc["_login_error"] = f"网络错误: {e}"
            return acc

        acc["_login_error"] = "令牌过期，请使用 /query mimo login 重新登录"
        return acc

    def _sync_re_login_account(self, acc: dict) -> dict:
        """同步：查询失败后重新登录。优先级：passToken > account+password"""
        acc["serviceToken"] = ""
        pass_token = acc.get("passToken", "")
        user_id = acc.get("userId", "")

        if pass_token:
            mi = self._create_mi_account(acc)
            try:
                user_id, service_token = mi.login_with_passtoken(user_id, pass_token)
                acc["userId"] = user_id
                acc["serviceToken"] = service_token
                return acc
            except PassTokenExpired:
                acc["passToken"] = ""
            except (OSError, StsError):
                pass

        account = acc.get("account", "")
        password = acc.get("password", "")
        if account and password:
            mi = self._create_mi_account(acc)
            try:
                result = mi.login_with_password(account, password)
                acc["userId"] = result["userId"]
                acc["passToken"] = result["passToken"]
                acc["serviceToken"] = result["serviceToken"]
                return acc
            except OtpRequired:
                acc["_otp_required"] = True
            except LoginError as e:
                acc["_login_error"] = f"重新登录失败: {e}"
            except (OSError, StsError) as e:
                acc["_login_error"] = f"网络错误: {e}"
            return acc

        acc["_login_error"] = "令牌过期，请使用 /query mimo login 重新登录"
        return acc

    def _sync_login_account(self, acc: dict, otp_code: str | None = None) -> dict:
        """同步：完整登录流程，返回凭据 dict"""
        mi = self._create_mi_account(acc)
        result = mi.login_with_password(
            acc["account"], acc["password"], otp_code=otp_code
        )
        return {
            "account": acc["account"],
            "password": acc["password"],
            "userId": result["userId"],
            "passToken": result["passToken"],
            "serviceToken": result["serviceToken"],
        }

    # ══════════════════════════════════════════
    #  查询相关
    # ══════════════════════════════════════════

    async def query_one(self, acc: dict) -> dict:
        """查询单个 MiMo 账号，失败时自动重登录并重试"""
        if acc.pop("_otp_required", False):
            return {
                "error": "需要短信验证，请在网页管理界面登录该账号"
            }

        login_error = acc.pop("_login_error", "")
        if login_error:
            return {"error": login_error}

        service_token = acc.get("serviceToken", "")
        user_id = acc.get("userId", "")

        # 如果没有 serviceToken，尝试自动获取
        if not service_token:
            acc = await self.ensure_account(acc)
            service_token = acc.get("serviceToken", "")
            user_id = acc.get("userId", "")
            
            # 检查是否有登录错误
            login_error = acc.pop("_login_error", "")
            if login_error:
                return {"error": login_error}
            
            if not service_token or not user_id:
                return {
                    "error": "无有效凭据，请检查账号配置"
                }

        ua = acc.get("ua", "")
        api_config = self._config.get("api", {})
        results = await query_mimo(
            service_token,
            user_id,
            ua,
            balance_url=api_config.get("balance_url"),
            usage_url=api_config.get("usage_url"),
            timeout=self._config.get("query_timeout", 15),
        )

        if not is_auth_error(results) and is_valid_response(results):
            return results

        acc = await self.re_login_account(acc)
        if acc.get("serviceToken"):
            results = await query_mimo(
                acc["serviceToken"],
                user_id,
                ua,
                balance_url=api_config.get("balance_url"),
                usage_url=api_config.get("usage_url"),
                timeout=self._config.get("query_timeout", 15),
            )

        return results

    async def query(self, account: dict, template: str | None = None) -> MimoResult:
        """查询单个账号"""
        label = self.get_account_label(account)
        use_template = template or self._default_template

        result_data = await self.query_one(account)
        if "error" in result_data:
            return MimoResult(
                success=False,
                account_name=label,
                data=result_data,
                error=result_data["error"],
                template=use_template,
            )

        return MimoResult(
            success=True,
            account_name=label,
            data=result_data,
            template=use_template,
        )
