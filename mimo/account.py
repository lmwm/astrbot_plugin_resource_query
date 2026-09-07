"""小米账号登录封装

参考 MiService (https://github.com/Yonsm/MiService) 的 miaccount.py 实现。
"""

import base64
import hashlib
import logging
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request

from ..http_utils import inject_cookie, new_opener, parse_resp
from .constants import DEFAULT_ACCOUNT_BASE
from .exceptions import LoginError, OtpRequired, PassTokenExpired, StsError

logger = logging.getLogger(__name__)

# OTP 验证用的 User-Agent（参考 MiService）
_UA_OTP = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)


class MiAccount:
    """小米账号登录封装"""

    def __init__(self, device_id: str, ua: str, account_base: str | None = None):
        self.device_id = device_id
        self.ua = ua
        self.account_base = account_base or DEFAULT_ACCOUNT_BASE
        # 缓存OTP会话状态，保持 opener/jar 在整个OTP流程中不变
        self._otp_session = None

    def login_with_passtoken(self, user_id: str, pass_token: str) -> tuple[str, str]:
        """使用 passToken 登录，返回 (userId, serviceToken)"""
        opener, jar = new_opener()
        for n, v in [
            ("sdkVersion", "3.9"),
            ("deviceId", self.device_id),
            ("userId", user_id),
            ("passToken", pass_token),
        ]:
            inject_cookie(jar, n, v)
        resp = self._serviceLogin(opener)
        code = resp.get("code")
        if code != 0:
            if code == 70016:
                raise PassTokenExpired(f"passToken 已过期 (code={code})")
            raise StsError(f"serviceLogin 失败 (code={code})")
        if not resp.get("userId"):
            raise PassTokenExpired("passToken 无效")
        service_token = self._sts(opener, jar, resp)
        return str(resp["userId"]), service_token

    def login_with_password(
        self, account: str, password: str, otp_code: str | None = None
    ) -> dict:
        """使用账号密码登录，返回含 userId/passToken/serviceToken 的 dict

        OTP 流程分两次调用：
        - 第一次（无 otp_code）：触发 OTP 发送，抛出 OtpRequired，缓存会话
        - 第二次（有 otp_code）：提交 OTP 码，使用缓存的会话继续登录
        """
        # === 第二次调用：提交 OTP 码 ===
        if otp_code and self._otp_session:
            session = self._otp_session
            self._otp_session = None

            opener = session["opener"]
            jar = session["jar"]
            notification_url = session["notification_url"]
            sid = session["sid"]

            # 提交 OTP 码
            self._submit_otp_code(opener, jar, notification_url, otp_code)

            # 重新调用 serviceLogin（此时 session 已有认证 cookies）
            resp = self._serviceLogin(opener)
            if resp.get("code") != 0:
                raise LoginError(f"OTP 验证后登录失败: {resp}")

            # 检查响应是否包含必要字段
            for key in ("userId", "passToken", "location", "nonce", "ssecurity"):
                if key not in resp:
                    raise LoginError(f"OTP 验证后登录响应缺少 '{key}': {resp}")

            service_token = self._sts(opener, jar, resp)
            return {
                "userId": str(resp["userId"]),
                "passToken": resp["passToken"],
                "serviceToken": service_token,
            }

        # === 第一次调用：开始登录 ===
        opener, jar = new_opener()
        for n, v in [("sdkVersion", "3.9"), ("deviceId", self.device_id)]:
            inject_cookie(jar, n, v)

        # 1. serviceLogin
        resp = self._serviceLogin(opener)
        if resp.get("code") == 0:
            # 已经登录（有 passToken cookie），直接获取 STS
            st = self._sts(opener, jar, resp)
            return {
                "userId": str(resp["userId"]),
                "passToken": resp.get("passToken", ""),
                "serviceToken": st,
            }

        if not resp.get("qs"):
            raise LoginError(f"serviceLogin 异常: code={resp.get('code')}")

        # 2. serviceLoginAuth2 — 提交账号密码
        resp2 = self._serviceLoginAuth2(opener, account, password, resp)
        if resp2.get("code") != 0:
            raise LoginError(f"密码认证失败: {resp2.get('desc', resp2)}")

        # 3. 如果需要 OTP
        if notification_url := resp2.get("notificationUrl"):
            logger.info("[login_with_password] 需要 OTP，缓存会话并触发验证码发送")
            # 缓存会话（同一个 opener/jar），后续提交 OTP 时继续使用
            self._otp_session = {
                "opener": opener,
                "jar": jar,
                "notification_url": notification_url,
                "sid": resp2.get("sid", "api-platform"),
            }
            # 触发 OTP 发送
            self._trigger_otp_send(opener, notification_url)
            raise OtpRequired(notification_url)

        # 4. 不需要 OTP，直接获取 STS
        for key in ("userId", "passToken", "location", "nonce", "ssecurity"):
            if key not in resp2:
                raise LoginError(f"登录响应缺少 '{key}': {resp2}")

        service_token = self._sts(opener, jar, resp2)
        return {
            "userId": str(resp2["userId"]),
            "passToken": resp2["passToken"],
            "serviceToken": service_token,
        }

    # ──────────────────────────────────────────────
    #  内部方法
    # ──────────────────────────────────────────────

    def _serviceLogin(self, opener, jar=None, extra_cookies=None) -> dict:
        """调用 /pass/serviceLogin"""
        url = f"{self.account_base}/pass/serviceLogin?sid=api-platform&_json=true"
        headers = {"User-Agent": self.ua}
        cookies = {"sdkVersion": "3.9", "deviceId": self.device_id}
        if extra_cookies:
            cookies.update(extra_cookies)
        if jar:
            for name, value in cookies.items():
                if value:
                    inject_cookie(jar, name, value, domain="account.xiaomi.com")
        try:
            with opener.open(Request(url, headers=headers), timeout=15) as r:
                return parse_resp(r.read())
        except Exception as e:
            return {"code": -1, "error": str(e)}

    def _serviceLoginAuth2(self, opener, account, password, login_resp) -> dict:
        """调用 /pass/serviceLoginAuth2 — 提交账号密码"""
        data = {
            "_json": "true",
            "qs": login_resp["qs"],
            "sid": login_resp["sid"],
            "_sign": login_resp["_sign"],
            "callback": login_resp["callback"],
            "user": account,
            "hash": hashlib.md5(password.encode()).hexdigest().upper(),
        }
        body = urlencode(data).encode()
        req = Request(
            f"{self.account_base}/pass/serviceLoginAuth2",
            data=body,
            headers={"User-Agent": self.ua},
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with opener.open(req, timeout=15) as r:
            return parse_resp(r.read())

    def _trigger_otp_send(self, opener, notification_url):
        """触发 OTP 验证码发送（参考 MiService _verify_otp 步骤 1-4）

        只负责发送验证码，不等待用户输入。
        """
        if not notification_url.startswith("http"):
            notification_url = self.account_base + notification_url
        headers = {"User-Agent": _UA_OTP}

        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(notification_url).query)
        context = q.get("context", [""])[0]
        sid_p = q.get("sid", ["api-platform"])[0]

        # Step 1: 打开 notificationUrl 建立验证会话
        try:
            with opener.open(Request(notification_url, headers=headers), timeout=15) as r:
                r.read()
        except HTTPError as e:
            if e.code == 401:
                logger.info("[_trigger_otp_send] notificationUrl 返回 401，OTP 已触发")
                return
            raise LoginError(f"打开 OTP 验证会话失败: HTTP {e.code}")
        except Exception as e:
            raise LoginError(f"打开 OTP 验证会话失败: {e}")

        # Step 2: 获取可用验证方式
        list_url = (
            f"{self.account_base}/identity/list"
            f"?sid={sid_p}&supportedMask=0&_locale=zh_CN&context={context}"
        )
        try:
            with opener.open(Request(list_url, headers=headers), timeout=15) as r:
                idata = parse_resp(r.read())
        except Exception as e:
            raise LoginError(f"获取验证方式失败: {e}")

        flag = idata.get("flag", 4)
        method = "Email" if flag == 8 else "Phone"

        # Step 3: 触发 OTP 发送
        verify_url = f"{self.account_base}/identity/auth/verify{method}?_flag={flag}&_json=true"
        try:
            with opener.open(Request(verify_url, headers=headers), timeout=15) as r:
                tresp = parse_resp(r.read())
        except Exception as e:
            raise LoginError(f"触发 {method} 验证码发送失败: {e}")
        if tresp.get("code") not in (0, None):
            tips = tresp.get("tips") or tresp.get("desc") or str(tresp)
            raise LoginError(tips)

        # Step 4: 发送短信
        if method == "Phone":
            body = urlencode({"retry": "0", "icode": "", "_json": "true"}).encode()
            req = Request(
                f"{self.account_base}/identity/auth/sendPhoneTicket",
                data=body,
                headers=headers,
                method="POST",
            )
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            try:
                with opener.open(req, timeout=15) as r:
                    sresp = parse_resp(r.read())
            except Exception as e:
                raise LoginError(f"发送短信验证码失败: {e}")
            if sresp.get("code") not in (0, None):
                tips = sresp.get("tips") or sresp.get("desc") or str(sresp)
                raise LoginError(tips)

        logger.info("[_trigger_otp_send] OTP 验证码发送完成")

    def _submit_otp_code(self, opener, jar, notification_url, code):
        """提交 OTP 验证码（参考 MiService _verify_otp 步骤 5-7）

        提交验证码、跟随 location、设置认证 cookies。
        """
        if not notification_url.startswith("http"):
            notification_url = self.account_base + notification_url
        headers = {"User-Agent": _UA_OTP}

        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(notification_url).query)
        context = q.get("context", [""])[0]
        sid_p = q.get("sid", ["api-platform"])[0]

        # 获取验证方式
        list_url = (
            f"{self.account_base}/identity/list"
            f"?sid={sid_p}&supportedMask=0&_locale=zh_CN&context={context}"
        )
        try:
            with opener.open(Request(list_url, headers=headers), timeout=15) as r:
                idata = parse_resp(r.read())
        except Exception:
            idata = {}

        flag = idata.get("flag", 4)
        method = "Email" if flag == 8 else "Phone"

        # 提交 OTP 码
        body = urlencode({
            "_flag": str(flag),
            "ticket": code.strip(),
            "trust": "false",
            "_json": "true",
        }).encode()
        req = Request(
            f"{self.account_base}/identity/auth/verify{method}?_dc={int(time.time() * 1000)}",
            data=body,
            headers=headers,
            method="POST",
        )
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with opener.open(req, timeout=15) as r:
                vresp = parse_resp(r.read())
        except HTTPError as e:
            if e.code == 401:
                logger.info("[_submit_otp_code] verify 返回 401，OTP 验证已完成")
                return
            raise

        # 跟随 location 设置认证 cookies
        location = vresp.get("location")
        if location:
            if not location.startswith("http"):
                location = self.account_base + location
            try:
                with opener.open(Request(location, headers=headers), timeout=15) as r:
                    r.read()
            except Exception as e:
                logger.warning(f"[_submit_otp_code] location 跟随异常: {e}")

        # 重新注入必要的 cookies
        inject_cookie(jar, "sdkVersion", "3.9", domain="account.xiaomi.com")
        inject_cookie(jar, "deviceId", self.device_id, domain="account.xiaomi.com")

        logger.info("[_submit_otp_code] OTP 验证码提交完成")

    def _sts(self, opener, jar, resp) -> str:
        """通过 STS 换取 serviceToken"""
        nonce = resp["nonce"]
        ssecurity = resp["ssecurity"]
        location = resp["location"]
        nsec = f"nonce={nonce}&{ssecurity}"
        sign = base64.b64encode(hashlib.sha1(nsec.encode()).digest()).decode()
        sts_url = f"{location}&clientSign={quote(sign)}"
        with opener.open(Request(sts_url, headers={"User-Agent": self.ua}), timeout=15) as r:
            r.read()
        for c in jar:
            if "serviceToken" in c.name:
                return c.value
        raise StsError("STS 响应中未找到 serviceToken")
