"""华数广电平台管理器"""

import asyncio
import json
from pathlib import Path
from urllib.request import Request

from ..base import BasePlatform
from ..http_utils import new_opener
from .constants import DEFAULT_BASE_URL, DEFAULT_HEADERS, DEFAULT_TEMPLATE
from .result import WasuResult
from .utils import fmt_gb, fmt_yuan


class WasuManager(BasePlatform):
    """华数广电平台管理器"""

    def __init__(self, plugin_dir: Path | None = None):
        self._plugin_dir = plugin_dir
        self._default_template = self._load_default_template()

    @property
    def platform_name(self) -> str:
        return "华数广电"

    @property
    def platform_icon(self) -> str:
        return "📺"

    def _load_default_template(self) -> str:
        """从模板文件夹加载默认模板"""
        if self._plugin_dir:
            tpl_path = self._plugin_dir / "templates" / "wasu_default.txt"
            if tpl_path.exists():
                try:
                    return tpl_path.read_text(encoding="utf-8")
                except OSError:
                    pass
        return DEFAULT_TEMPLATE

    async def query(self, account: dict, template: str | None = None) -> WasuResult:
        """查询华数广电账号"""
        use_template = template or self._default_template
        user_key = account.get("user_key", "")
        token = account.get("token", "")
        phone = account.get("phone", "")
        sign = account.get("sign", "")
        ua = account.get("ua", "")

        if not user_key or not token or not phone:
            return WasuResult(
                success=False,
                account_name=self.get_account_label(account),
                data={},
                error="缺少必要参数（user_key, token, phone）",
                template=use_template,
            )

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, self._do_query, user_key, token, phone, sign, ua
            )
            return WasuResult(
                success=True,
                account_name=self.get_account_label(account),
                data=data,
                template=use_template,
            )
        except Exception as e:
            return WasuResult(
                success=False,
                account_name=self.get_account_label(account),
                data={},
                error=str(e),
                template=use_template,
            )

    def _do_query(self, user_key: str, token: str, phone: str, sign: str, ua: str = "") -> dict:
        """执行查询（同步）"""
        headers = {**DEFAULT_HEADERS}
        if ua:
            headers["User-Agent"] = ua

        def _post(path: str, payload: dict) -> dict:
            body = json.dumps(payload, separators=(",", ":"))
            opener, _ = new_opener()
            req = Request(
                DEFAULT_BASE_URL + path,
                data=body.encode("utf-8"),
                headers={**headers, "x-sign": sign},
                method="POST",
            )
            with opener.open(req, timeout=10) as r:
                return json.loads(r.read())["data"]

        payload = {"userKey": user_key, "token": token, "phoneNo": phone}

        # 查询话费余额
        fee = _post("/msm-local-hub/api/v3/gd/query/fee", payload)

        # 查询流量/通话资源
        res = _post("/msm-local-hub/api/v3/gd/query/resource", payload)

        # 解析余额
        balance_data = {
            "balance": fmt_yuan(fee.get("BALANCE", 0)),
            "month_fee": fmt_yuan(fee.get("CURREAL_FEE", 0)),
            "arrears": fmt_yuan(fee.get("SPAY_FEE", 0)),
        }

        # 解析流量
        ext = res.get("USER_EXT_RES_LIST", [{}])[0]
        data_items = [r for r in res.get("USER_RES_LIST", []) if r.get("ITEM_TYPE_CODE") == "3"]
        voice_items = [r for r in res.get("USER_RES_LIST", []) if r.get("ITEM_TYPE_CODE") == "2"]

        total_high = sum(int(r.get("HIGH_FEE", 0)) for r in data_items)
        total_bal = sum(int(r.get("BALANCE", 0)) for r in data_items)
        total_used = total_high - total_bal

        traffic_items = []
        for r in data_items:
            used = int(r.get("HIGH_FEE", 0)) - int(r.get("BALANCE", 0))
            traffic_items.append({
                "name": r.get("DISCNT_NAME", ""),
                "total": fmt_gb(int(r.get("HIGH_FEE", 0))),
                "used": fmt_gb(used),
                "remain": fmt_gb(int(r.get("BALANCE", 0))),
                "is_carry": "结转" in r.get("DISCNT_NAME", ""),
            })

        traffic_data = {
            "total_used": fmt_gb(ext.get("ADDUP_TOTAL_VALUE", 0)),
            "total": fmt_gb(total_high),
            "used": fmt_gb(total_used),
            "remain": fmt_gb(total_bal),
            "items": traffic_items,
        }

        # 解析语音
        voice_data = []
        for r in voice_items:
            voice_data.append({
                "name": r.get("DISCNT_NAME", ""),
                "total": r.get("HIGH_FEE", "0"),
                "remain": r.get("BALANCE", "0"),
            })

        return {
            "balance": balance_data,
            "traffic": traffic_data,
            "voice": voice_data,
            "query_time": fee.get("X_SYSDATE", ""),
        }
