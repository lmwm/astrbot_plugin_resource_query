"""MiMo 平台常量 - 这些是默认值，实际值从配置文件加载"""

# 默认内置模板（兜底用）
DEFAULT_TEMPLATE = """📋 {label}
────────────────
  余额        {balance}元
  赠送        {gift_balance}元
  输入        {input_token}
  输出        {output_token}
  缓存        {cache_token}
  本月费用    {monthly_cost}元
  累计费用    {total_cost}元"""

# 默认 API 地址（兜底用）
DEFAULT_ACCOUNT_BASE = "https://account.xiaomi.com"
DEFAULT_BALANCE_URL = "https://platform.xiaomimimo.com/api/v1/balance"
DEFAULT_USAGE_URL = "https://platform.xiaomimimo.com/api/v1/usage"
