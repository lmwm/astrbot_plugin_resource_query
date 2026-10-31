# 功能模块基类
#
# 所有功能模块（MiMo 查询 / 华数查询 / JM 下载 / 插件更新 ...）都继承此基类。
#
# 模块自治原则：
#   1. 每个模块管理自己的配置、账号、模板、查询、指令与 Views 接口；
#   2. 模块之间不直接依赖，需要协作时通过注册中心按名称取用；
#   3. 模块开关由 AstrBot 原生配置管理，模块自身配置由 Views 管理。
#
# 新增模块的步骤：
#   1. 在 `modules/` 下新建目录，实现 `XxxModule(ModuleBase)`；
#   2. 按需覆盖 `supports_*` 属性与 `get_*_fields()`，声明自己的能力；
#   3. 在 `main.py` 的模块清单中登记一行。
#   Views 前端依据模块声明的 schema 自动渲染配置页，无需改动前端代码。

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..common import utils as common_utils
from ..common.utils import get_platform_path
from .accounts import AccountStore
from .config_store import ConfigStore
from .result import QueryResult

if TYPE_CHECKING:
    from .registry import ModuleRegistry


class ModuleBase(ABC):
    # 功能模块基类

    def __init__(self, plugin_dir: Path, plugin_name: str) -> None:
        # 初始化模块；配置目录与账号存储在构造时一次性定位
        self._plugin_dir = plugin_dir
        self._plugin_name = plugin_name
        self._registry: ModuleRegistry | None = None
        self._context: Any = None
        self._config_store = ConfigStore(self.get_config_path())
        self._account_store = AccountStore(
            self.get_config_path(), self.account_file_prefix
        )

    #  元信息（子类必须实现）

    @property
    @abstractmethod
    def module_name(self) -> str:
        # 模块唯一标识（小写，用作配置目录名与接口前缀）
        pass

    @property
    @abstractmethod
    def module_title(self) -> str:
        # 模块显示名（Views 导航与帮助信息中使用）
        pass

    @property
    def module_icon(self) -> str:
        # 模块图标（Views 导航中使用）
        return ""

    @property
    def module_desc(self) -> str:
        # 模块一句话描述
        return ""

    #  能力声明（子类按需覆盖）

    @property
    def supports_accounts(self) -> bool:
        # 是否管理多账号（决定 Views 是否渲染账号列表）
        return False

    @property
    def supports_template(self) -> bool:
        # 是否支持消息模板（决定 Views 是否渲染模板编辑器）
        return False

    @property
    def supports_query(self) -> bool:
        # 是否提供查询能力
        return False

    @property
    def supports_login(self) -> bool:
        # 是否支持在 Views 中登录（决定是否显示「登录」按钮）
        return False

    @property
    def supports_test(self) -> bool:
        # 是否支持在 Views 中测试凭据（决定是否显示「测试」按钮）
        return False

    @property
    def account_file_prefix(self) -> str:
        # 账号配置文件名前缀（子类可覆盖，如 "mimo_"）
        return ""

    @property
    def account_label(self) -> str:
        # 账号称谓，用于指令文案（子类可覆盖为「MiMo 账号」等）
        return f"{self.module_title}账号"

    @property
    def variables_editable(self) -> bool:
        # 模板变量是否允许在 Views 中编辑；代码内固定的变量返回 False
        return True

    #  注册中心

    def set_context(self, context: Any) -> None:
        # 注入 AstrBot 上下文（子类按需使用）
        self._context = context

    def set_registry(self, registry: ModuleRegistry | None) -> None:
        # 绑定所属注册中心
        self._registry = registry

    def get_other_module(self, module_name: str) -> ModuleBase | None:
        # 获取其他模块实例
        if self._registry:
            return self._registry.get_module(module_name)
        return None

    async def on_load(self) -> None:
        # 插件加载完成后的异步初始化（子类按需覆盖）
        # 读取一次配置，顺带把旧的 config.json 迁移为 config.yaml
        self.load_module_config()

    async def on_unload(self) -> None:
        # 插件卸载前的清理（子类按需覆盖）
        pass

    #  路径

    def get_data_path(self) -> Path:
        # 获取本插件的数据目录（不存在时自动创建）
        return common_utils.get_data_path(self._plugin_name)

    def get_config_path(self) -> Path:
        # 获取本模块的配置目录（不存在时自动创建）
        return get_platform_path(self._plugin_name, self.module_name)

    #  模块配置（Views 管理）

    def get_default_config(self) -> dict:
        # 模块默认配置（子类覆盖）
        return {}

    def get_config_fields(self) -> list[dict]:
        # 模块配置的字段定义（子类覆盖）
        return []

    def get_config_groups(self) -> list[dict]:
        # 配置字段的分组：Views 里每组单独一页（子类按需覆盖）
        return []

    def load_module_config(self) -> dict:
        # 读取模块配置（默认值与已保存值合并）
        return self._config_store.load(self.get_default_config())

    def save_module_config(self, config: dict) -> bool:
        return self._config_store.save(config)

    #  账号管理（supports_accounts 为 True 时实现）

    def get_account_fields(self) -> list[dict]:
        # 账号表单的字段定义（子类覆盖）
        return []

    def get_account_groups(self) -> list[dict]:
        # 账号字段的分组定义（子类覆盖）
        return []

    def get_accounts(self) -> list[dict]:
        # 读取本模块全部账号；每项带 `_filename` 供稳定删除
        return self._account_store.list()

    def save_accounts(self, accounts: list[dict]) -> bool:
        return self._account_store.save(accounts)

    def delete_account(self, filename: str) -> dict | None:
        return self._account_store.delete(filename)

    #  模板（supports_template 为 True 时实现）

    def get_default_template(self) -> str:
        # 默认消息模板（子类覆盖）
        return ""

    def get_account_template(self, acc: dict) -> str:
        # 获取账号使用的模板
        template = str(acc.get("template") or "").strip()
        return template or self.get_default_template()

    def get_var_definitions(self) -> dict[str, str]:
        # 模板变量名到中文描述的映射（子类覆盖）
        return {}

    def get_var_samples(self) -> dict[str, str]:
        # 变量示例值，供 Views 的消息模板预览使用（子类覆盖）
        return {}

    #  查询（supports_query 为 True 时实现）

    async def query(self, account: dict) -> QueryResult:
        # 查询单个账号（子类覆盖）
        raise NotImplementedError(f"{self.module_name} 未实现查询能力")

    async def query_all(self) -> list[QueryResult]:
        # 查询本模块全部账号；单个账号异常不会中断其余账号
        results: list[QueryResult] = []

        for acc in self.get_accounts():
            label = self.account_display_name(acc) or "未命名"
            try:
                results.append(await self.query(acc))
            except Exception as e:
                results.append(
                    QueryResult(
                        success=False,
                        platform=self.module_title,
                        account_name=label,
                        error=f"{type(e).__name__}: {e}",
                    )
                )

        return results

    def render(self, result: QueryResult) -> str:
        # 把查询结果渲染为可直接发送的文本
        return result.to_text()

    #  指令（子类按需覆盖）

    def get_commands(self) -> list[dict]:
        # 本模块提供的指令列表（子类覆盖）
        return []

    async def handle_command(self, command: str, args: list[str], event: Any):
        # 默认实现：多账号模块自动获得 ls / del / 全量查询 / 单账号查询
        if not self.supports_accounts:
            yield event.plain_result(
                f"❌ 模块「{self.module_title}」不支持指令 /{command}"
            )
            return

        accounts = self.get_accounts()

        if args and args[0].lower() == "ls":
            yield event.plain_result(self._account_list_text(accounts))
            return

        if args and args[0].lower() == "del":
            async for result in self._delete_command(args, event, accounts):
                yield result
            return

        if not args:
            if not accounts:
                yield event.plain_result(self._no_account_text())
                return
            yield event.plain_result(f"正在查询所有 {self.account_label}...")
            for acc in accounts:
                yield event.plain_result(self.render(await self.query(acc)))
            return

        account = self.find_account(args[0])
        if not account:
            yield event.plain_result(
                f"× 未找到账号: {args[0]}\n使用 /{self.module_name} ls 查看所有账号"
            )
            return

        yield event.plain_result("正在查询...")
        yield event.plain_result(self.render(await self.query(account)))

    def describe_account(self, acc: dict, index: int) -> str:
        # 列表项文案；子类可覆盖以追加登录状态或手机号
        return self.account_display_name(acc) or f"{self.account_label}{index}"

    def account_display_name(self, acc: dict) -> str:
        return str(acc.get("name") or acc.get("account") or acc.get("phone") or "")

    def find_account(self, identifier: str) -> dict | None:
        # 按名称、账号、手机号或文件名查找账号
        for acc in self.get_accounts():
            for key in ("name", "account", "phone", "_filename"):
                if identifier == str(acc.get(key) or ""):
                    return acc
        return None

    def _no_account_text(self) -> str:
        return f"× 还没有配置 {self.account_label}\n请在网页管理界面添加账号"

    def _account_list_text(self, accounts: list[dict]) -> str:
        if not accounts:
            return self._no_account_text()

        lines = [f"共 {len(accounts)} 个 {self.account_label}:"]
        for index, acc in enumerate(accounts, start=1):
            lines.append(f"  {index}. {self.describe_account(acc, index)}")
        return "\n".join(lines)

    async def _delete_command(self, args: list[str], event: Any, accounts: list[dict]):
        # 按序号或名称删除账号
        if len(args) < 2:
            yield event.plain_result(f"用法: /{self.module_name} del <序号或名称>")
            return

        target = args[1]
        account: dict | None = None

        if target.isdigit():
            index = int(target) - 1
            if 0 <= index < len(accounts):
                account = accounts[index]
        else:
            account = self.find_account(target)

        if not account:
            yield event.plain_result(f"× 未找到账号: {target}")
            return

        deleted = self.delete_account(str(account.get("_filename", "")))
        if not deleted:
            yield event.plain_result("× 删除失败")
            return

        name = self.account_display_name(deleted) or target
        yield event.plain_result(f"√ 已删除: {name}")

    #  Views 支持

    def config_payload(self, config: dict) -> dict:
        # 返回给 Views 的配置；子类可追加只读字段
        return config

    def accept_config_payload(self, payload: dict, config: dict) -> dict:
        # 过滤待保存字段；默认全部接受
        return payload

    async def api_get_config(self):
        from astrbot.api.web import json_response

        return json_response(self.config_payload(self.load_module_config()))

    async def api_save_config(self):
        from astrbot.api.web import error_response, json_response, request

        payload = await request.json(default={})
        if not isinstance(payload, dict) or not payload:
            return error_response("缺少配置数据")

        config = self.load_module_config()
        config.update(self.accept_config_payload(payload, config))

        if not self.save_module_config(config):
            return error_response("保存失败")

        return json_response({"status": "ok"})

    async def api_reset_config(self):
        # 把模块配置恢复为 config.yaml 中的默认值
        from astrbot.api.web import error_response, json_response

        config = self.get_default_config()
        if not self.save_module_config(config):
            return error_response("恢复默认失败")

        return json_response({"status": "ok", "config": self.config_payload(config)})

    def get_web_apis(self) -> list[dict]:
        # 默认提供配置读写与恢复默认；子类用 super().get_web_apis() + [...] 追加自有接口
        return [
            {
                "path": "config",
                "handler": self.api_get_config,
                "methods": ["GET"],
                "desc": "获取模块配置",
            },
            {
                "path": "config",
                "handler": self.api_save_config,
                "methods": ["POST"],
                "desc": "保存模块配置",
            },
            {
                "path": "config/reset",
                "handler": self.api_reset_config,
                "methods": ["POST"],
                "desc": "恢复模块默认配置",
            },
        ]

    def get_page_schema(self) -> dict:
        # Views 渲染所需的模块描述
        #
        #         前端依据此 schema 通用渲染配置页，因此新增模块通常无需改动前端。
        return {
            "name": self.module_name,
            "title": self.module_title,
            "icon": self.module_icon,
            "desc": self.module_desc,
            "supports_accounts": self.supports_accounts,
            "supports_template": self.supports_template,
            "supports_query": self.supports_query,
            "supports_login": self.supports_login,
            "supports_test": self.supports_test,
            "variables_editable": self.variables_editable,
            "config_fields": self.get_config_fields(),
            "config_groups": self.get_config_groups(),
            "account_fields": self.get_account_fields(),
            "account_groups": self.get_account_groups(),
            "variables": self.get_var_definitions(),
            "variable_samples": self.get_var_samples(),
            "default_template": self.get_default_template()
            if self.supports_template
            else "",
        }
