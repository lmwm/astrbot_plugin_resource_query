"""测试 userId 参数的必要性"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 直接导入需要的模块，避免导入整个 mimo 包
from http_utils import new_opener, inject_cookie, parse_resp
from urllib.request import Request


class TestMiAccount:
    """测试用的 MiAccount"""
    
    ACCOUNT_BASE = "https://account.xiaomi.com"
    
    def __init__(self, device_id: str, ua: str):
        self.device_id = device_id
        self.ua = ua
    
    def _service_login(self, opener) -> dict:
        url = f"{self.ACCOUNT_BASE}/pass/serviceLogin?sid=api-platform&_json=true"
        headers = {"User-Agent": self.ua}
        with opener.open(Request(url, headers=headers), timeout=15) as r:
            return parse_resp(r.read())
    
    def _sts(self, opener, jar, resp) -> str:
        import base64
        import hashlib
        from urllib.parse import quote
        
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
        raise Exception("STS 响应中未找到 serviceToken")
    
    def login_with_passtoken(self, user_id: str, pass_token: str) -> tuple:
        """使用 passToken 登录，返回 (userId, serviceToken)"""
        opener, jar = new_opener()
        
        if not user_id:
            # 只设置 deviceId 和 passToken
            for n, v in [("deviceId", self.device_id), ("passToken", pass_token)]:
                inject_cookie(jar, n, v)
            resp = self._service_login(opener)
            code = resp.get("code")
            if code != 0:
                raise Exception(f"serviceLogin 失败 (code={code})")
            user_id = resp.get("userId")
            if not user_id:
                raise Exception("passToken 无效，无法获取 userId")
        else:
            # 设置所有 cookies
            for n, v in [("deviceId", self.device_id), ("userId", user_id), ("passToken", pass_token)]:
                inject_cookie(jar, n, v)
            resp = self._service_login(opener)
            code = resp.get("code")
            if code != 0:
                raise Exception(f"serviceLogin 失败 (code={code})")
            if not resp.get("userId"):
                raise Exception("passToken 无效")
        
        service_token = self._sts(opener, jar, resp)
        return user_id, service_token


async def test_query():
    # 读取测试配置
    config_path = Path(__file__).parent / "测试.json"
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    user_id = config.get("userId", "")
    pass_token = config.get("passToken", "")
    service_token = config.get("serviceToken", "")
    device_id = config.get("device_id", "")
    ua = config.get("ua", "")
    
    print("=" * 60)
    print("测试 userId 参数的必要性")
    print("=" * 60)
    
    # 测试查询函数
    async def query_mimo_test(st, uid, ua_str):
        def _query():
            opener, jar = new_opener()
            for n, v, d in [
                ("userId", uid, "platform.xiaomimimo.com"),
                ("serviceToken", st, "platform.xiaomimimo.com"),
            ]:
                inject_cookie(jar, n, v, domain=d)
            results = {}
            for key, url in [("balance", "https://platform.xiaomimimo.com/api/v1/balance"), 
                             ("usage", "https://platform.xiaomimimo.com/api/v1/usage")]:
                try:
                    with opener.open(Request(url, headers={"User-Agent": ua_str}), timeout=15) as r:
                        results[key] = parse_resp(r.read())
                except Exception as e:
                    results[key] = {"code": -1, "error": str(e)}
            return results
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _query)
    
    # 测试 1: 使用完整凭据查询（有 userId）
    print("\n[测试 1] 使用完整凭据查询（有 userId）")
    print(f"  userId: {user_id}")
    print(f"  serviceToken: {service_token[:30]}...")
    
    try:
        result = await query_mimo_test(service_token, user_id, ua)
        if "error" in result:
            print(f"  [FAIL] 查询失败: {result['error']}")
        else:
            balance = result.get("balance", {}).get("data", {})
            print(f"  [OK] 查询成功")
            print(f"  余额: {balance.get('balance', '?')}")
    except Exception as e:
        print(f"  [FAIL] 查询异常: {e}")
    
    # 测试 2: 使用空 userId 查询
    print("\n[测试 2] 使用空 userId 查询")
    print(f"  userId: (空)")
    print(f"  serviceToken: {service_token[:30]}...")
    
    try:
        result = await query_mimo_test(service_token, "", ua)
        if "error" in result:
            print(f"  [FAIL] 查询失败: {result['error']}")
        else:
            balance = result.get("balance", {}).get("data", {})
            print(f"  [OK] 查询成功")
            print(f"  余额: {balance.get('balance', '?')}")
    except Exception as e:
        print(f"  [FAIL] 查询异常: {e}")
    
    # 测试 3: 使用 passToken 登录（有 userId）
    print("\n[测试 3] 使用 passToken 登录（有 userId）")
    print(f"  userId: {user_id}")
    print(f"  passToken: {pass_token[:30]}...")
    
    mi = TestMiAccount(device_id, ua)
    try:
        new_user_id, new_service_token = mi.login_with_passtoken(user_id, pass_token)
        print(f"  [OK] 登录成功")
        print(f"  获取的 userId: {new_user_id}")
        print(f"  获取的 serviceToken: {new_service_token[:30]}...")
        
        # 使用新获取的凭据查询
        result = await query_mimo_test(new_service_token, new_user_id, ua)
        if "error" in result:
            print(f"  [FAIL] 查询失败: {result['error']}")
        else:
            balance = result.get("balance", {}).get("data", {})
            print(f"  [OK] 查询成功")
            print(f"  余额: {balance.get('balance', '?')}")
    except Exception as e:
        print(f"  [FAIL] 登录异常: {e}")
    
    # 测试 4: 使用 passToken 登录（无 userId）
    print("\n[测试 4] 使用 passToken 登录（无 userId）")
    print(f"  userId: (空)")
    print(f"  passToken: {pass_token[:30]}...")
    
    mi = TestMiAccount(device_id, ua)
    try:
        new_user_id, new_service_token = mi.login_with_passtoken("", pass_token)
        print(f"  [OK] 登录成功")
        print(f"  自动获取的 userId: {new_user_id}")
        print(f"  获取的 serviceToken: {new_service_token[:30]}...")
        
        # 使用新获取的凭据查询
        result = await query_mimo_test(new_service_token, new_user_id, ua)
        if "error" in result:
            print(f"  [FAIL] 查询失败: {result['error']}")
        else:
            balance = result.get("balance", {}).get("data", {})
            print(f"  [OK] 查询成功")
            print(f"  余额: {balance.get('balance', '?')}")
    except Exception as e:
        print(f"  [FAIL] 登录异常: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_query())
