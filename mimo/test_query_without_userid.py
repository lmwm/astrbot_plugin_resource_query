"""测试查询是否需要 userId"""

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


async def test_query():
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
    
    async def query_mimo(st, uid, ua_str):
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
    
    def print_result(label, result):
        print(f"\n{label}")
        print("-" * 40)
        
        # 余额
        bal = result.get("balance", {}).get("data", {})
        bal_code = result.get("balance", {}).get("code", -1)
        if bal_code == 0 and bal:
            print(f"  余额: {bal.get('balance', '?')} 元")
            print(f"  赠送余额: {bal.get('giftBalance', '?')} 元")
        else:
            print(f"  余额: 获取失败 (code={bal_code})")
        
        # 用量
        usage = result.get("usage", {}).get("data", {})
        usage_code = result.get("usage", {}).get("code", -1)
        if usage_code == 0 and usage:
            tok = usage.get("tokenUsage", {})
            cost = usage.get("costUsage", {})
            limit = usage.get("accountRateLimit", {})
            
            print(f"  输入 Token: {fmt_num(tok.get('inputToken', 0))}")
            print(f"  输出 Token: {fmt_num(tok.get('outputToken', 0))}")
            print(f"  缓存 Token: {fmt_num(tok.get('cacheToken', 0))}")
            print(f"  本月费用: {cost.get('currentMonthCost', '?')} 元")
            print(f"  累计费用: {cost.get('totalCost', '?')} 元")
            print(f"  TPM: {fmt_num(limit.get('tpm', 0))}")
            print(f"  RPM: {fmt_num(limit.get('rpm', 0))}")
            print(f"  并发: {limit.get('concurrency', '-')}")
        else:
            print(f"  用量: 获取失败 (code={usage_code})")
        
        # 检查错误
        for key in ["balance", "usage"]:
            resp = result.get(key, {})
            if resp.get("code", 0) != 0:
                print(f"  [{key} 错误] {resp}")
    
    print("=" * 60)
    print("测试查询是否需要 userId")
    print("=" * 60)
    
    # 测试 1: 使用 userId 查询
    print("\n[测试 1] 使用 userId 查询")
    print(f"  userId: {user_id}")
    result1 = await query_mimo(service_token, user_id, ua)
    print_result("结果（有 userId）:", result1)
    
    # 测试 2: 不使用 userId 查询
    print("\n[测试 2] 不使用 userId 查询")
    print(f"  userId: (空)")
    result2 = await query_mimo(service_token, "", ua)
    print_result("结果（无 userId）:", result2)
    
    # 对比
    print("\n" + "=" * 60)
    print("对比结果")
    print("=" * 60)
    
    bal1 = result1.get("balance", {}).get("data", {})
    bal2 = result2.get("balance", {}).get("data", {})
    usage1 = result1.get("usage", {}).get("data", {})
    usage2 = result2.get("usage", {}).get("data", {})
    
    print(f"\n余额: 有userId={bal1.get('balance', '?')} vs 无userId={bal2.get('balance', '?')}")
    print(f"本月费用: 有userId={usage1.get('costUsage', {}).get('currentMonthCost', '?')} vs 无userId={usage2.get('costUsage', {}).get('currentMonthCost', '?')}")
    print(f"输入Token: 有userId={fmt_num(usage1.get('tokenUsage', {}).get('inputToken', 0))} vs 无userId={fmt_num(usage2.get('tokenUsage', {}).get('inputToken', 0))}")
    
    # 结论
    print("\n" + "=" * 60)
    print("结论")
    print("=" * 60)
    
    bal1_ok = result1.get("balance", {}).get("code", -1) == 0
    bal2_ok = result2.get("balance", {}).get("code", -1) == 0
    usage1_ok = result1.get("usage", {}).get("code", -1) == 0
    usage2_ok = result2.get("usage", {}).get("code", -1) == 0
    
    if bal1_ok and bal2_ok and usage1_ok and usage2_ok:
        print("查询不需要 userId，两种方式都能成功获取数据")
    elif bal1_ok and usage1_ok and (not bal2_ok or not usage2_ok):
        print("查询需要 userId，没有 userId 时查询失败")
    else:
        print("部分查询成功，需要进一步分析")


if __name__ == "__main__":
    asyncio.run(test_query())
