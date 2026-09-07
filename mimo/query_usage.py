"""查询 MiMo 使用量"""

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


async def query_usage():
    # 读取测试配置
    config_path = Path(__file__).parent / "测试.json"
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    user_id = config.get("userId", "")
    service_token = config.get("serviceToken", "")
    ua = config.get("ua", "")
    
    # 格式化数字
    def fmt_num(n):
        n = int(n or 0)
        if n >= 100_000_000:
            return f"{n / 100_000_000:.1f}亿"
        if n >= 10_000:
            return f"{n / 10_000:.1f}万"
        return f"{n:,}"
    
    def _query():
        opener, jar = new_opener()
        for n, v, d in [
            ("userId", user_id, "platform.xiaomimimo.com"),
            ("serviceToken", service_token, "platform.xiaomimimo.com"),
        ]:
            inject_cookie(jar, n, v, domain=d)
        results = {}
        for key, url in [("balance", "https://platform.xiaomimimo.com/api/v1/balance"), 
                         ("usage", "https://platform.xiaomimimo.com/api/v1/usage")]:
            try:
                with opener.open(Request(url, headers={"User-Agent": ua}), timeout=15) as r:
                    results[key] = parse_resp(r.read())
            except Exception as e:
                results[key] = {"code": -1, "error": str(e)}
        return results
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _query)
    
    print("=" * 60)
    print("MiMo 使用量查询结果")
    print("=" * 60)
    
    # 余额信息
    bal = result.get("balance", {}).get("data", {})
    if bal:
        print(f"\n[余额]")
        print(f"  余额: {bal.get('balance', '?')} 元")
        print(f"  赠送余额: {bal.get('giftBalance', '?')} 元")
    else:
        print(f"\n[余额] 获取失败")
        print(f"  balance response: {result.get('balance', {})}")
    
    # 用量信息
    usage = result.get("usage", {}).get("data", {})
    if usage:
        tok = usage.get("tokenUsage", {})
        cost = usage.get("costUsage", {})
        limit = usage.get("accountRateLimit", {})
        
        print(f"\n[Token 用量]")
        print(f"  输入 Token: {fmt_num(tok.get('inputToken', 0))}")
        print(f"  输出 Token: {fmt_num(tok.get('outputToken', 0))}")
        print(f"  缓存 Token: {fmt_num(tok.get('cacheToken', 0))}")
        
        print(f"\n[费用]")
        print(f"  本月费用: {cost.get('currentMonthCost', '?')} 元")
        print(f"  累计费用: {cost.get('totalCost', '?')} 元")
        
        print(f"\n[限额]")
        print(f"  TPM: {fmt_num(limit.get('tpm', 0))}")
        print(f"  RPM: {fmt_num(limit.get('rpm', 0))}")
        print(f"  并发: {limit.get('concurrency', '-')}")
    else:
        print(f"\n[用量] 获取失败")
        print(f"  usage response: {result.get('usage', {})}")
    
    # 检查是否有错误
    for key in ["balance", "usage"]:
        resp = result.get(key, {})
        if "error" in resp:
            print(f"\n[{key} 错误] {resp['error']}")
        elif resp.get("code", 0) != 0:
            print(f"\n[{key} 错误] code={resp.get('code')}, message={resp.get('message', '')}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(query_usage())
