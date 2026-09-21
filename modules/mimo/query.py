"""MiMo 平台查询逻辑"""

import asyncio
from urllib.request import Request

from ...http_utils import inject_cookie, new_opener, parse_resp


async def query_mimo(
    service_token: str,
    user_id: str,
    ua: str,
    balance_url: str,
    usage_url: str,
    timeout: int = 15,
) -> dict:
    """查询 MiMo 平台余额和用量，返回原始 API 响应

    Args:
        service_token: 账号的 serviceToken。
        user_id: 小米账号 User ID。
        ua: User-Agent。
        balance_url: 余额查询接口地址。
        usage_url: 用量查询接口地址。
        timeout: 单次请求超时秒数。

    Returns:
        包含 balance 与 usage 两个原始 API 响应的字典。
    """

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

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _query)


# 明确的认证失效信号（避免把普通提示误判为凭据过期）
_AUTH_ERROR_CODES = {401, 70016}
_AUTH_ERROR_KEYWORDS = (
    "unauthorized",
    "invalid token",
    "token expired",
    "token过期",
    "token 过期",
    "登录失效",
    "未登录",
    "请先登录",
)


def is_auth_error(results: dict) -> bool:
    """检测接口响应是否属于认证失效

    Args:
        results: 接口原始响应字典。

    Returns:
        是否属于认证失效。
    """
    for value in results.values():
        if not isinstance(value, dict):
            continue
        if value.get("code") in _AUTH_ERROR_CODES:
            return True

        message = str(value.get("message") or value.get("desc") or "").lower()
        if any(keyword in message for keyword in _AUTH_ERROR_KEYWORDS):
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
