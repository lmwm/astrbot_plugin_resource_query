"""华数广电平台常量"""

# 默认 API 地址
DEFAULT_BASE_URL = "https://ups.wasu.cn"

# 默认请求头
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 16; 23127PN0CC Build/BP2A.250605.031.A3; wv) ",
    "content-type": "application/json;charset=utf-8",
}

# 默认内置模板（兜底用）
DEFAULT_TEMPLATE = """📺 {label}
────────────────
💰 账户余额: {balance}
   当月话费: {month_fee}
   欠费: {arrears}

📶 本月累计使用: {total_used}
   总流量: {total} | 已用: {used} | 剩余: {remain}

🕐 查询时间: {query_time}"""
