"""MiMo 平台管理器 - 统一管理登录、查询等功能

注意：此管理器是 MiMo 模块的内部实现，不对外暴露。
MiMoModule 通过组合方式使用此管理器。

登录流程：
  1. 账号密码 → PassToken + User ID（login_with_password）
  2. PassToken → ServiceToken（login_with_passtoken）
"""

import asyncio
from pathlib import Path

from .account import MiAccount
from .exceptions import LoginError, OtpRequired, PassTokenExpired, StsError
from .query import is_auth_error, is_valid_response, query_mimo
from .utils import load_config


class MimoManager:
    """MiMo 平台管理器（内部实现）

    负责处理 MiMo 平台的登录和查询逻辑。
    """

    def __init__(self, plugin_dir: Path):
        """初始化 MiMo 管理器

        Args:
            plugin_dir: 插件目录路径
        """
        self._plugin_dir = plugin_dir
        self._config = load_config(plugin_dir)
        # 缓存 MiAccount 实例，用于保持 OTP 会话状态
        self._mi_account_cache: dict[str, MiAccount] = {}

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
        """同步：完整登录流程（在线程中调用）

        流程：
          1. 账号密码 → PassToken + User ID
          2. PassToken → ServiceToken

        Returns:
            dict: {"userId", "passToken", "serviceToken"}
        """
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

    def _get_service_token(self, mi: MiAccount, user_id: str, pass_token: str, acc: dict) -> None:
        """通过 PassToken 获取 ServiceToken 并更新账号配置

        Args:
            mi: MiAccount 实例
            user_id: 用户 ID
            pass_token: PassToken
            acc: 账号配置字典（会被修改）
        """
        user_id, service_token = mi.login_with_passtoken(user_id, pass_token)
        acc["userId"] = user_id
        acc["serviceToken"] = service_token

    def _try_pass_token_login(self, mi: MiAccount, user_id: str, pass_token: str, acc: dict) -> bool:
        """尝试使用 passToken 获取 serviceToken

        Args:
            mi: MiAccount 实例
            user_id: 用户 ID
            pass_token: PassToken
            acc: 账号配置字典（会被修改）

        Returns:
            是否成功获取 serviceToken
        """
        try:
            self._get_service_token(mi, user_id, pass_token, acc)
            return True
        except PassTokenExpired:
            acc["passToken"] = ""
            return False
        except (OSError, StsError):
            return False

    def _try_password_login(self, mi: MiAccount, acc: dict) -> bool:
        """尝试使用账号密码登录

        流程：
          1. 账号密码 → PassToken + User ID
          2. PassToken → ServiceToken

        Args:
            mi: MiAccount 实例
            acc: 账号配置字典（会被修改）

        Returns:
            是否成功登录
        """
        account = acc.get("account", "")
        password = acc.get("password", "")

        if not account or not password:
            acc["_login_error"] = "令牌过期，请使用 /mimo otp <验证码> 或重新登录"
            return False

        try:
            # 第一步：账号密码 → PassToken + User ID
            result = mi.login_with_password(account, password)
            acc["userId"] = result["userId"]
            acc["passToken"] = result["passToken"]

            # 第二步：PassToken → ServiceToken
            self._get_service_token(mi, result["userId"], result["passToken"], acc)
            return True
        except OtpRequired:
            acc["_otp_required"] = True
            return False
        except LoginError as e:
            acc["_login_error"] = f"登录失败: {e}"
            return False
        except (OSError, StsError) as e:
            acc["_login_error"] = f"网络错误: {e}"
            return False

    def _sync_ensure_account(self, acc: dict) -> dict:
        """同步：确保账号有可用凭据

        优先级：serviceToken > passToken > account+password
        """
        service_token = acc.get("serviceToken", "")
        pass_token = acc.get("passToken", "")
        user_id = acc.get("userId", "")

        # 已有 serviceToken，直接返回
        if service_token and user_id:
            return acc

        # 尝试用 passToken 获取 serviceToken
        if pass_token:
            mi = self._create_mi_account(acc)
            if self._try_pass_token_login(mi, user_id, pass_token, acc):
                return acc

        # 尝试用账号密码登录
        mi = self._create_mi_account(acc)
        self._try_password_login(mi, acc)
        return acc

    def _sync_re_login_account(self, acc: dict) -> dict:
        """同步：查询失败后重新登录

        优先级：passToken > account+password
        """
        acc["serviceToken"] = ""
        pass_token = acc.get("passToken", "")
        user_id = acc.get("userId", "")

        # 尝试用 passToken 获取 serviceToken
        if pass_token:
            mi = self._create_mi_account(acc)
            if self._try_pass_token_login(mi, user_id, pass_token, acc):
                return acc

        # 尝试用账号密码登录
        mi = self._create_mi_account(acc)
        self._try_password_login(mi, acc)
        return acc

    def _sync_login_account(self, acc: dict, otp_code: str | None = None) -> dict:
        """同步：完整登录流程，返回凭据 dict

        流程：
          1. 账号密码 → PassToken + User ID（或 OTP 验证）
          2. PassToken → ServiceToken

        Returns:
            dict: {"account", "password", "userId", "passToken", "serviceToken"}
        """
        mi = self._create_mi_account(acc)

        # 第一步：账号密码 → PassToken + User ID
        result = mi.login_with_password(
            acc["account"], acc["password"], otp_code=otp_code
        )

        # 第二步：PassToken → ServiceToken
        user_id, service_token = mi.login_with_passtoken(
            result["userId"], result["passToken"]
        )

        return {
            "account": acc["account"],
            "password": acc["password"],
            "userId": user_id,
            "passToken": result["passToken"],
            "serviceToken": service_token,
        }

    def get_pending_otp_account(self) -> str | None:
        """获取等待 OTP 验证的账号名称"""
        for key, mi in self._mi_account_cache.items():
            if mi._otp_session is not None:
                # key 格式是 "account:device_id"
                return key.split(":")[0]
        return None

    def submit_otp(self, otp_code: str) -> dict:
        """提交 OTP 验证码，完成登录

        流程：
          1. 提交 OTP 验证码，获取 PassToken + User ID
          2. 通过 PassToken 获取 ServiceToken

        Args:
            otp_code: OTP 验证码。

        Returns:
            登录成功的凭据 dict: {"userId", "passToken", "serviceToken"}

        Raises:
            LoginError: 登录失败。
        """
        # 找到有 OTP 会话的 MiAccount
        for key, mi in self._mi_account_cache.items():
            if mi._otp_session is not None:
                # 第一步：提交 OTP，获取 PassToken + User ID
                result = mi.login_with_password("", "", otp_code=otp_code)

                # 第二步：PassToken → ServiceToken
                user_id, service_token = mi.login_with_passtoken(
                    result["userId"], result["passToken"]
                )

                return {
                    "userId": user_id,
                    "passToken": result["passToken"],
                    "serviceToken": service_token,
                }

        raise LoginError("没有等待 OTP 验证的账号")

    # ══════════════════════════════════════════
    #  查询相关
    # ══════════════════════════════════════════

    async def query_one(self, acc: dict) -> dict:
        """查询单个 MiMo 账号，失败时自动重登录并重试"""
        if acc.pop("_otp_required", False):
            return {
                "error": "需要短信验证，请使用 /mimo otp <验证码> 提交验证码"
            }

        login_error = acc.pop("_login_error", "")
        if login_error:
            return {"error": login_error}

        service_token = acc.get("serviceToken", "")
        user_id = acc.get("userId", "")

        # 如果没有 serviceToken，尝试自动获取
        if not service_token:
            acc = await self.ensure_account(acc)

            # 检查是否需要 OTP 验证
            if acc.pop("_otp_required", False):
                return {
                    "error": "需要短信验证，请使用 /mimo otp <验证码> 提交验证码"
                }

            # 检查是否有登录错误
            login_error = acc.pop("_login_error", "")
            if login_error:
                return {"error": login_error}

            service_token = acc.get("serviceToken", "")
            user_id = acc.get("userId", "")

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
