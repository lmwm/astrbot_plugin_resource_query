# 华数广电平台模块
#
# 继承 ModuleBase，实现华数广电的账号管理与流量/话费查询。
#
# 接口说明：
#   POST /msm-local-hub/api/v3/gd/query/fee       话费余额
#   POST /msm-local-hub/api/v3/gd/query/resource  流量与语音资源
#
# 注意：接口用 `code` 字段表示业务结果，`code != 0` 时响应中**不含 data**，
# 因此必须显式校验业务码，不能直接取 data。

from __future__ import annotations

import asyncio
import json
from urllib.request import Request

from ...core.module import ModuleBase
from ...http_utils import new_opener
from .constants import DEFAULT_BASE_URL, DEFAULT_HEADERS
from .result import WasuResult
from .utils import fmt_gb, fmt_yuan, get_default_template
from .utils import get_var_definitions as _load_var_definitions

# 账号表单字段
_ACCOUNT_FIELDS = [
    {"key": "name", "label": "账号名称", "type": "text", "hint": "留空则显示手机号"},
    {"key": "phone", "label": "手机号", "type": "text"},
    {"key": "user_key", "label": "User Key", "type": "text"},
    {"key": "token", "label": "Token", "type": "password", "hint": "失效后需重新获取"},
    {"key": "sign", "label": "Sign", "type": "password", "hint": "可选"},
]

# 业务码：token 失效
_CODE_TOKEN_INVALID = 14


class WasuApiError(Exception):
    # 华数接口调用错误
    pass


class WasuModule(ModuleBase):
    # 华数广电查询模块

    # ══════════════════════════════════════════
    #  元信息
    # ══════════════════════════════════════════

    @property
    def module_name(self) -> str:
        # 模块标识
        return "wasu"

    @property
    def module_title(self) -> str:
        # 模块显示名
        return "华数查询"

    @property
    def module_icon(self) -> str:
        # 模块图标
        return "◎"

    @property
    def module_desc(self) -> str:
        # 模块描述
        return "华数广电流量 / 话费 / 余量查询"

    # ══════════════════════════════════════════
    #  能力声明
    # ══════════════════════════════════════════

    @property
    def supports_accounts(self) -> bool:
        # 支持多账号管理
        return True

    @property
    def supports_template(self) -> bool:
        # 支持消息模板
        return True

    @property
    def supports_query(self) -> bool:
        # 支持查询
        return True

    @property
    def supports_test(self) -> bool:
        # 支持在 Views 中测试凭据
        return True

    @property
    def account_label(self) -> str:
        return "华数账号"

    # ══════════════════════════════════════════
    #  字段定义
    # ══════════════════════════════════════════

    def get_account_fields(self) -> list[dict]:
        # 账号表单字段定义
        #
        #         Returns:
        #             字段列表。
        return _ACCOUNT_FIELDS

    def get_var_definitions(self) -> dict[str, str]:
        # 模板变量说明（来自 modules/wasu/config.yaml）
        #
        #         Returns:
        #             变量名到中文描述的映射。
        return _load_var_definitions()

    def get_default_template(self) -> str:
        # 默认消息模板
        #
        #         Returns:
        #             来自 config.yaml 的默认模板。
        return get_default_template()

    async def query(self, account: dict) -> WasuResult:
        # 查询单个华数账号
        label = self.account_display_name(account) or "华数账号"
        template = self.get_account_template(account)

        user_key = str(account.get("user_key") or "").strip()
        token = str(account.get("token") or "").strip()
        phone = str(account.get("phone") or "").strip()

        if not user_key or not token or not phone:
            return WasuResult(
                success=False,
                account_name=label,
                error="缺少必要参数（User Key / Token / 手机号）",
                template=template,
            )

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None,
                self._do_query,
                user_key,
                token,
                phone,
                str(account.get("sign") or ""),
                str(account.get("ua") or ""),
            )
        except WasuApiError as e:
            return WasuResult(
                success=False, account_name=label, error=str(e), template=template
            )
        except Exception as e:
            return WasuResult(
                success=False,
                account_name=label,
                error=f"{type(e).__name__}: {e}",
                template=template,
            )

        return WasuResult(
            success=True, account_name=label, data=data, template=template
        )

    def _do_query(
        self,
        user_key: str,
        token: str,
        phone: str,
        sign: str = "",
        ua: str = "",
    ) -> dict:
        # 执行查询（同步，在线程池中运行）
        #
        #         Args:
        #             user_key: 用户 key。
        #             token: 认证 token。
        #             phone: 手机号。
        #             sign: 签名。
        #             ua: User-Agent。
        #
        #         Returns:
        #             结构化查询数据。
        #
        #         Raises:
        #             WasuApiError: 接口返回业务错误或缺少数据。
        base_url = DEFAULT_BASE_URL
        headers = {**DEFAULT_HEADERS, "x-sign": sign}
        if ua:
            headers["User-Agent"] = ua

        def _post(path: str, payload: dict) -> dict:
            # 发起 POST 请求并校验业务码
            #
            #             Args:
            #                 path: 接口路径。
            #                 payload: 请求体。
            #
            #             Returns:
            #                 响应中的 data 字段。
            #
            #             Raises:
            #                 WasuApiError: 业务码非 0 或缺少 data。
            body = json.dumps(payload, separators=(",", ":"))
            opener, _ = new_opener()
            req = Request(
                base_url + path,
                data=body.encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with opener.open(req, timeout=10) as r:
                resp = json.loads(r.read())

            if not isinstance(resp, dict):
                raise WasuApiError("接口返回格式异常")

            code = resp.get("code")
            if code not in (0, None):
                if code == _CODE_TOKEN_INVALID:
                    raise WasuApiError(
                        "凭据已失效（token 错误），请在网页管理界面重新填写账号信息"
                    )
                message = resp.get("message") or resp.get("msg") or "未知原因"
                raise WasuApiError(f"接口返回错误 code={code}: {message}")

            data = resp.get("data")
            if not isinstance(data, dict):
                raise WasuApiError("接口未返回数据")

            return data

        payload = {"userKey": user_key, "token": token, "phoneNo": phone}
        fee = _post("/msm-local-hub/api/v3/gd/query/fee", payload)
        resource = _post("/msm-local-hub/api/v3/gd/query/resource", payload)

        return self._parse_response(fee, resource)

    @staticmethod
    def _parse_response(fee: dict, resource: dict) -> dict:
        # 解析话费与资源接口响应
        #
        #         Args:
        #             fee: fee 接口返回的 data。
        #             resource: resource 接口返回的 data。
        #
        #         Returns:
        #             结构化的余额、流量与语音数据。
        balance = {
            "balance": fmt_yuan(fee.get("BALANCE", 0)),
            "month_fee": fmt_yuan(fee.get("CURREAL_FEE", 0)),
            "arrears": fmt_yuan(fee.get("SPAY_FEE", 0)),
        }

        ext_list = resource.get("USER_EXT_RES_LIST") or [{}]
        ext = ext_list[0] if ext_list and isinstance(ext_list[0], dict) else {}

        res_items = resource.get("USER_RES_LIST") or []
        data_items = [r for r in res_items if r.get("ITEM_TYPE_CODE") == "3"]
        voice_items = [r for r in res_items if r.get("ITEM_TYPE_CODE") == "2"]

        total_high = sum(int(r.get("HIGH_FEE", 0) or 0) for r in data_items)
        total_balance = sum(int(r.get("BALANCE", 0) or 0) for r in data_items)

        items = []
        for r in data_items:
            high = int(r.get("HIGH_FEE", 0) or 0)
            remain = int(r.get("BALANCE", 0) or 0)
            name = str(r.get("DISCNT_NAME", ""))
            items.append(
                {
                    "name": name,
                    "total": fmt_gb(high),
                    "used": fmt_gb(high - remain),
                    "remain": fmt_gb(remain),
                    "is_carry": "结转" in name,
                }
            )

        voice = [
            {
                "name": str(r.get("DISCNT_NAME", "")),
                "total": r.get("HIGH_FEE", "0"),
                "remain": r.get("BALANCE", "0"),
            }
            for r in voice_items
        ]

        return {
            "balance": balance,
            "traffic": {
                "total_used": fmt_gb(ext.get("ADDUP_TOTAL_VALUE", 0)),
                "total": fmt_gb(total_high),
                "used": fmt_gb(total_high - total_balance),
                "remain": fmt_gb(total_balance),
                "items": items,
            },
            "voice": voice,
            "query_time": fee.get("X_SYSDATE", ""),
        }

    # ══════════════════════════════════════════
    #  指令
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        # 本模块指令列表
        #
        #         Returns:
        #             指令定义列表。
        return [{"name": "wasu", "desc": "华数广电查询：/wasu [ls|del|账号]"}]

    def describe_account(self, acc: dict, index: int) -> str:
        name = self.account_display_name(acc) or f"华数账号{index}"
        return f"{name} | 手机号: {acc.get('phone', '未填写')}"

    # ══════════════════════════════════════════
    #  Views 接口
    # ══════════════════════════════════════════

    def get_web_apis(self) -> list[dict]:
        # 配置读写由基类提供，这里只追加凭据测试
        return super().get_web_apis() + [
            {
                "path": "test",
                "handler": self._api_test,
                "methods": ["POST"],
                "desc": "测试凭据是否可用",
            },
        ]

    async def _api_test(self):
        # 测试凭据是否可用
        #
        #         Returns:
        #             JSON 响应。
        from astrbot.api.web import json_response, request

        payload = await request.json(default={})
        if not isinstance(payload, dict) or not payload:
            return json_response({"status": "error", "message": "缺少账号配置"})

        result = await self.query(payload)

        if not result.success:
            return json_response(
                {
                    "status": "error",
                    "message": result.error or "查询失败",
                }
            )

        return json_response({"status": "ok", "message": "凭据有效"})
