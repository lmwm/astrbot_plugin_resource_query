"""测试只通过 passToken 获取 userId 和 serviceToken"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 直接导入需要的模块
from http_utils import new_opener, inject_cookie, parse_resp
from urllib.request import Request

ACCOUNT_BASE = "https://account.xiaomi.com"


async def test_passtoken():
    # 读取测试配置
    config_path = Path(__file__).parent / "测试.json"
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    pass_token = config.get("passToken", "")
    known_user_id = config.get("userId", "")
    device_id = config.get("device_id", "")
    ua = config.get("ua", "")
    
    print("=" * 60)
    print("测试只通过 passToken 获取 userId 和 serviceToken")
    print("=" * 60)
    
    def service_login(opener, cookies):
        """发起 serviceLogin 请求"""
        url = f"{ACCOUNT_BASE}/pass/serviceLogin?sid=api-platform&_json=true"
        headers = {"User-Agent": ua}
        for name, value in cookies.items():
            if value:
                inject_cookie(opener[1], name, value, domain="account.xiaomi.com")
        with opener[0].open(Request(url, headers=headers), timeout=15) as r:
            return parse_resp(r.read())
    
    def sts(opener, resp):
        """通过 STS 换取 serviceToken"""
        import base64
        import hashlib
        from urllib.parse import quote
        
        nonce = resp["nonce"]
        ssecurity = resp["ssecurity"]
        location = resp["location"]
        nsec = f"nonce={nonce}&{ssecurity}"
        sign = base64.b64encode(hashlib.sha1(nsec.encode()).digest()).decode()
        sts_url = f"{location}&clientSign={quote(sign)}"
        with opener[0].open(Request(sts_url, headers={"User-Agent": ua}), timeout=15) as r:
            r.read()
        for c in opener[1]:
            if "serviceToken" in c.name:
                return c.value
        return None
    
    # 测试 1: 只用 deviceId + passToken（无 userId）
    print("\n[测试 1] 只用 deviceId + passToken（无 userId）")
    print(f"  deviceId: {device_id}")
    print(f"  passToken: {pass_token[:30]}...")
    
    opener = new_opener()
    try:
        resp = service_login(opener, {
            "sdkVersion": "3.9",
            "deviceId": device_id,
            "passToken": pass_token,
        })
        print(f"  响应 code: {resp.get('code')}")
        if resp.get("code") == 0:
            print(f"  userId: {resp.get('userId')}")
            st = sts(opener, resp)
            print(f"  serviceToken: {st[:30] if st else 'None'}...")
            print(f"  [OK] 成功")
        else:
            print(f"  [FAIL] 失败: {resp.get('description', resp.get('desc', ''))}")
    except Exception as e:
        print(f"  [FAIL] 异常: {e}")
    
    # 测试 2: 用已知的 userId + passToken
    print("\n[测试 2] 用已知的 userId + passToken")
    print(f"  userId: {known_user_id}")
    print(f"  passToken: {pass_token[:30]}...")
    
    opener = new_opener()
    try:
        resp = service_login(opener, {
            "sdkVersion": "3.9",
            "deviceId": device_id,
            "userId": known_user_id,
            "passToken": pass_token,
        })
        print(f"  响应 code: {resp.get('code')}")
        if resp.get("code") == 0:
            print(f"  userId: {resp.get('userId')}")
            st = sts(opener, resp)
            print(f"  serviceToken: {st[:30] if st else 'None'}...")
            print(f"  [OK] 成功")
        else:
            print(f"  [FAIL] 失败: {resp.get('description', resp.get('desc', ''))}")
    except Exception as e:
        print(f"  [FAIL] 异常: {e}")
    
    # 测试 3: 尝试用空 userId
    print("\n[测试 3] 尝试用空 userId")
    print(f"  userId: (空字符串)")
    print(f"  passToken: {pass_token[:30]}...")
    
    opener = new_opener()
    try:
        resp = service_login(opener, {
            "sdkVersion": "3.9",
            "deviceId": device_id,
            "userId": "",
            "passToken": pass_token,
        })
        print(f"  响应 code: {resp.get('code')}")
        if resp.get("code") == 0:
            print(f"  userId: {resp.get('userId')}")
            st = sts(opener, resp)
            print(f"  serviceToken: {st[:30] if st else 'None'}...")
            print(f"  [OK] 成功")
        else:
            print(f"  [FAIL] 失败: {resp.get('description', resp.get('desc', ''))}")
    except Exception as e:
        print(f"  [FAIL] 异常: {e}")
    
    # 测试 4: 尝试用 passToken 作为 userId
    print("\n[测试 4] 尝试用 passToken 的前几位作为 userId")
    print(f"  passToken: {pass_token[:30]}...")
    
    opener = new_opener()
    try:
        # 不设置 userId，只设置 passToken
        inject_cookie(opener[1], "sdkVersion", "3.9", domain="account.xiaomi.com")
        inject_cookie(opener[1], "deviceId", device_id, domain="account.xiaomi.com")
        inject_cookie(opener[1], "passToken", pass_token, domain="account.xiaomi.com")
        
        url = f"{ACCOUNT_BASE}/pass/serviceLogin?sid=api-platform&_json=true"
        req = Request(url, headers={"User-Agent": ua})
        with opener[0].open(req, timeout=15) as r:
            resp = parse_resp(r.read())
        
        print(f"  响应 code: {resp.get('code')}")
        if resp.get("code") == 0:
            print(f"  userId: {resp.get('userId')}")
            st = sts(opener, resp)
            print(f"  serviceToken: {st[:30] if st else 'None'}...")
            print(f"  [OK] 成功")
        else:
            print(f"  [FAIL] 失败: {resp.get('description', resp.get('desc', ''))}")
            print(f"  完整响应: {resp}")
    except Exception as e:
        print(f"  [FAIL] 异常: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_passtoken())
