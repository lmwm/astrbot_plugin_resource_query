"""华数广电平台模块

继承 ModuleBase，实现华数广电平台的账号管理和流量/话费查询功能。

设计原则：
1. 模块自治：华数模块管理自己的配置、账号、查询逻辑
2. 统一接口：通过 ModuleBase 提供统一的接口供总管理模块调用
3. 模块隔离：华数模块不直接访问其他模块，通过注册中心通信
"""

import asyncio
import json
from pathlib import Path
from urllib.request import Request

from ...core.module import ModuleBase
from ...http_utils import new_opener
from .constants import DEFAULT_BASE_URL, DEFAULT_HEADERS
from .result import WasuResult
from .utils import fmt_gb, fmt_yuan, load_default_template


class WasuModule(ModuleBase):
    """华数广电平台模块

    继承 ModuleBase，实现华数广电平台的账号管理和流量/话费查询功能。
    """

    def __init__(self, plugin_dir: Path, plugin_name: str):
        """初始化华数广电模块

        Args:
            plugin_dir: 插件目录路径
            plugin_name: 插件名称
        """
        super().__init__(plugin_dir, plugin_name)
        self._default_template = self._load_default_template()

    @property
    def module_name(self) -> str:
        """模块名称"""
        return "wasu"

    @property
    def module_icon(self) -> str:
        """模块图标"""
        return ""

    @property
    def module_desc(self) -> str:
        """模块描述"""
        return "华数广电流量/话费查询"

    def _load_default_template(self) -> str:
        """从配置文件加载默认模板"""
        return load_default_template()

    def get_default_template(self) -> str:
        """获取默认模板（覆盖基类方法）

        优先从 config.yaml 加载默认模板。

        Returns:
            默认模板内容
        """
        return self._default_template

    # ══════════════════════════════════════════
    #  查询接口（实现基类抽象方法）
    # ══════════════════════════════════════════

    async def query(self, account: dict) -> dict:
        """查询单个华数广电账号

        Args:
            account: 账号配置

        Returns:
            查询结果字典
        """
        label = account.get("name") or account.get("phone") or "华数账号"
        # 获取模板：优先使用账号自定义模板，否则使用默认模板
        template = self.get_account_template(account)
        if not template:
            template = self._default_template

        user_key = account.get("user_key", "")
        token = account.get("token", "")
        phone = account.get("phone", "")
        sign = account.get("sign", "")
        ua = account.get("ua", "")

        if not user_key or not token or not phone:
            return {
                "success": False,
                "account_name": label,
                "error": "缺少必要参数（user_key, token, phone）",
                "template": template,
            }

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, self._do_query, user_key, token, phone, sign, ua
            )
            return {
                "success": True,
                "account_name": label,
                "data": data,
                "template": template,
            }
        except Exception as e:
            return {
                "success": False,
                "account_name": label,
                "error": str(e),
                "template": template,
            }

    def _do_query(self, user_key: str, token: str, phone: str, sign: str, ua: str = "") -> dict:
        """执行查询（同步）

        Args:
            user_key: 用户 key
            token: 认证 token
            phone: 手机号
            sign: 签名
            ua: User-Agent

        Returns:
            查询数据
        """
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

    # ══════════════════════════════════════════
    #  指令支持
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        """获取华数广电模块提供的指令列表

        Returns:
            指令定义列表
        """
        return [
            {
                "name": "wasu",
                "desc": "华数广电查询指令",
                "handler": "handle_wasu_command"
            }
        ]

    async def handle_command(self, command: str, args: list[str], event) -> None:
        """处理华数广电指令

        Args:
            command: 指令名称
            args: 指令参数
            event: AstrBot 事件对象
        """
        if command == "wasu":
            async for result in self._handle_wasu_command(args, event):
                yield result

    async def _handle_wasu_command(self, args: list[str], event):
        """处理华数广电指令的具体实现

        Args:
            args: 指令参数
            event: AstrBot 事件对象
        """
        accounts = self.get_accounts()

        # /wasu ls — 列出所有账号
        if args and args[0].lower() == "ls":
            if not accounts:
                yield event.plain_result("❌ 还没有配置华数账号\n请在网页管理界面添加账号")
                return
            lines = [f"共 {len(accounts)} 个华数账号:"]
            for i, acc in enumerate(accounts):
                name = acc.get("name") or acc.get("phone") or f"华数账号{i+1}"
                lines.append(f"  {i + 1}. {name} | 手机号: {acc.get('phone', '无')}")
            yield event.plain_result("\n".join(lines))
            return

        # /wasu del <序号或名称> — 删除指定账号
        if args and args[0].lower() == "del":
            if len(args) < 2:
                yield event.plain_result("用法: /wasu del <序号或名称>")
                return

            del_arg = args[1]

            # 尝试按序号删除
            if del_arg.isdigit():
                del_idx = int(del_arg) - 1
                if 0 <= del_idx < len(accounts):
                    deleted = self.delete_account(del_idx)
                    if deleted:
                        name = deleted.get("name") or deleted.get("phone") or "未知"
                        yield event.plain_result(f"✅ 已删除: {name}")
                    else:
                        yield event.plain_result("❌ 删除失败")
                    return

            # 按名称删除
            for i, acc in enumerate(accounts):
                name = acc.get("name") or acc.get("phone") or ""
                if name == del_arg:
                    deleted = self.delete_account(i)
                    if deleted:
                        yield event.plain_result(f"✅ 已删除: {name}")
                    else:
                        yield event.plain_result("❌ 删除失败")
                    return

            yield event.plain_result(f"❌ 未找到账号: {del_arg}")
            return

        # /wasu — 查询所有账号
        if not args:
            if not accounts:
                yield event.plain_result("❌ 还没有配置华数账号\n请在网页管理界面添加账号")
                return
            yield event.plain_result("🔍 正在查询所有华数账号...")

            for acc in accounts:
                name = acc.get("name") or acc.get("phone") or "华数账号"
                try:
                    result = await self.query(acc)
                    if result.get("success"):
                        wr = WasuResult(
                            success=True,
                            account_name=name,
                            data=result.get("data", {}),
                            template=result.get("template")
                        )
                        yield event.plain_result(wr.to_text())
                    else:
                        yield event.plain_result(f"{name}\n❌ {result.get('error')}")
                except Exception as e:
                    yield event.plain_result(f"{name}\n❌ 查询失败: {e}")
            return

        # /wasu <名称> — 查询指定账号
        query_arg = args[0]

        # 按名称查找
        for acc in accounts:
            name = acc.get("name") or acc.get("phone") or ""
            if name == query_arg:
                yield event.plain_result("🔍 正在查询...")
                try:
                    result = await self.query(acc)
                    if result.get("success"):
                        wr = WasuResult(
                            success=True,
                            account_name=name,
                            data=result.get("data", {}),
                            template=result.get("template")
                        )
                        yield event.plain_result(wr.to_text())
                    else:
                        yield event.plain_result(f"{name}\n❌ {result.get('error')}")
                except Exception as e:
                    yield event.plain_result(f"{name}\n❌ 查询失败: {e}")
                return

        yield event.plain_result(f"❌ 未找到账号: {query_arg}\n使用 /wasu ls 查看所有账号")
