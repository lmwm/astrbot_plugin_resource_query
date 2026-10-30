# 全局 Views 接口
#
# 把各模块的账号、模板变量与页面描述汇总给前端；
# 具体业务仍由模块实现，这里只做聚合、参数校验与响应包装。

from __future__ import annotations

from ..common.utils import load_json_file, save_json_file
from .registry import ModuleRegistry

# 模板变量配置文件（与模块配置目录同级）
_VAR_CONFIG_FILE = "var_config.json"


class GlobalWebApi:
    # 全局接口集合：模块列表、账号、模板变量

    def __init__(self, registry: ModuleRegistry, version_provider) -> None:
        self._registry = registry
        self._version = version_provider

    def routes(self) -> list[tuple]:
        # 每项为 (路径, 处理函数, 方法列表, 描述)
        return [
            ("modules", self.get_modules, ["GET"], "获取已启用模块及其页面描述"),
            ("accounts", self.get_accounts, ["GET"], "获取所有模块的账号"),
            ("accounts", self.save_accounts, ["POST"], "保存指定模块的账号"),
            ("accounts/delete", self.delete_account, ["POST"], "删除指定账号"),
            ("template-vars", self.get_template_vars, ["GET"], "获取模板变量定义"),
            ("template-vars", self.save_template_vars, ["POST"], "保存模板变量定义"),
        ]

    async def get_modules(self):
        from astrbot.api.web import json_response

        return json_response(
            {
                "version": self._version(),
                "modules": [
                    module.get_page_schema()
                    for module in self._registry.get_all_modules()
                ],
            }
        )

    async def get_accounts(self):
        from astrbot.api.web import json_response

        accounts: list[dict] = []
        for module in self._registry.get_all_modules():
            for account in module.get_accounts():
                account["platform"] = module.module_name
                accounts.append(account)

        return json_response({"accounts": accounts})

    async def save_accounts(self):
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        platform = str(payload.get("platform") or "").strip()
        accounts = payload.get("accounts")

        module = self._registry.get_module(platform)
        if not module:
            return error_response(f"模块 {platform or '(空)'} 未启用")

        if not isinstance(accounts, list):
            return error_response("accounts 必须是数组")

        if not module.save_accounts(accounts):
            return error_response("保存失败")

        return json_response({"status": "ok"})

    async def delete_account(self):
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        platform = str(payload.get("platform") or "").strip()
        filename = str(payload.get("filename") or "").strip()

        if not platform or not filename:
            return error_response("缺少 platform 或 filename 参数")

        module = self._registry.get_module(platform)
        if not module:
            return error_response(f"模块 {platform} 未启用")

        deleted = module.delete_account(filename)
        if deleted is None:
            return error_response("账号不存在或删除失败")

        name = (
            deleted.get("name")
            or deleted.get("account")
            or deleted.get("phone")
            or filename
        )
        return json_response({"status": "ok", "deleted": name})

    async def get_template_vars(self):
        from astrbot.api.web import json_response

        result: dict[str, dict] = {}

        for module in self._registry.get_all_modules():
            declared = module.get_var_definitions()
            if not declared:
                continue

            saved = load_json_file(module.get_config_path() / _VAR_CONFIG_FILE) or {}
            saved_map = {
                item["name"]: item
                for item in (saved.get("variables") or [])
                if isinstance(item, dict) and item.get("name")
            }

            variables = [
                {
                    "name": name,
                    "desc": saved_map.get(name, {}).get("desc") or desc,
                    "default": saved_map.get(name, {}).get("default", ""),
                    "show": saved_map.get(name, {}).get("show", True),
                }
                for name, desc in declared.items()
            ]

            # 用户在 Views 中额外添加的变量也一并保留
            variables.extend(
                item for name, item in saved_map.items() if name not in declared
            )

            result[module.module_name] = {"variables": variables}

        return json_response(result)

    async def save_template_vars(self):
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        platform = str(payload.get("platform") or "").strip()
        variables = payload.get("variables")

        module = self._registry.get_module(platform)
        if not module:
            return error_response(f"模块 {platform or '(空)'} 未启用")

        if not isinstance(variables, list):
            return error_response("variables 必须是数组")

        path = module.get_config_path() / _VAR_CONFIG_FILE
        if not save_json_file(path, {"variables": variables}):
            return error_response("保存失败")

        return json_response({"status": "ok"})
