"""MiMo 平台查询逻辑"""

import asyncio
from urllib.request import Request

from ...http_utils import inject_cookie, new_opener, parse_resp
from .constants import DEFAULT_BALANCE_URL, DEFAULT_USAGE_URL


async def query_mimo(
    service_token: str,
    user_id: str,
    ua: str,
    balance_url: str | None = None,
    usage_url: str | None = None,
    timeout: int = 15,
) -> dict:
    """查询 MiMo 平台余额和用量，返回原始 API 响应"""
    balance_url = balance_url or DEFAULT_BALANCE_URL
    usage_url = usage_url or DEFAULT_USAGE_URL

    def _query():
        opener, jar = new_opener()
        for n, v, d in [
            ("userId", user_id, "platform.xiaomimimo.com"),
            ("serviceToken", service_token, "platform.xiaomimimo.com"),
        ]:
            inject_cookie(jar, n, v, domain=d)
        results = {}
        for key, url in [("balance", balance_url), ("usage", usage_url)]:
            try:
                with opener.open(
                    Request(url, headers={"User-Agent": ua}),
                    timeout=timeout,
                ) as r:
                    results[key] = parse_resp(r.read())
            except (OSError, TimeoutError) as e:
                results[key] = {"code": -1, "error": str(e)}
        return results

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _query)


def is_auth_error(results: dict) -> bool:
    """检测 API 响应是否为认证失败（401 / token 相关错误）"""
    for v in results.values():
        if not isinstance(v, dict):
            continue
        if v.get("code") == 401:
            return True
        msg = str(v.get("message", "")).lower()
        if "auth" in msg or "token" in msg:
            return True
    return False


def is_valid_response(results: dict) -> bool:
    """检测 API 响应是否包含有效数据（非空/非错误）"""
    for v in results.values():
        if not isinstance(v, dict):
            continue
        if v.get("code") == -1:
            return False
        if v.get("code") not in (0, None):
            return False
    return True
