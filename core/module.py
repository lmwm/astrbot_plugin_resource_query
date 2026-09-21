"""功能模块基类

所有功能模块（MiMo 查询 / 华数查询 / JM 下载 / 插件更新 ...）都继承此基类。

模块自治原则：
  1. 每个模块管理自己的配置、账号、模板、查询、指令与 Pages 接口；
  2. 模块之间不直接依赖，需要协作时通过注册中心按名称取用；
  3. 模块开关由 AstrBot 原生配置管理，模块自身配置由 Pages 管理。

新增模块的步骤：
  1. 在 `modules/` 下新建目录，实现 `XxxModule(ModuleBase)`；
  2. 按需覆盖 `supports_*` 属性与 `get_*_fields()`，声明自己的能力；
  3. 在 `main.py` 的模块清单中登记一行。
  Pages 前端依据模块声明的 schema 自动渲染配置页，无需改动前端代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..common.utils import (
    get_account_filename,
    get_platform_path,
    load_json_file,
    save_json_file,
)

if TYPE_CHECKING:
    from .registry import ModuleRegistry

# 模块自身配置文件名
MODULE_CONFIG_FILE = "config.json"

# 配置目录中非账号的保留文件
RESERVED_FILES = {"config.json", "var_config.json"}


class ModuleBase(ABC):
    """功能模块基类

    Attributes:
        plugin_name: 所属插件名（用于定位数据目录）。
        module_name: 模块唯一标识，同时作为配置目录名与 Pages 路由前缀。
    """

    def __init__(self, plugin_dir: Path, plugin_name: str) -> None:
        """初始化模块

        Args:
            plugin_dir: 插件目录路径。
            plugin_name: 插件名称。
        """
        self._plugin_dir = plugin_dir
        self._plugin_name = plugin_name
        self._registry: ModuleRegistry | None = None
        self._context: Any = None

    # ══════════════════════════════════════════
    #  元信息（子类必须实现）
    # ══════════════════════════════════════════

    @property
    @abstractmethod
    def module_name(self) -> str:
        """模块唯一标识（小写，用作配置目录名与接口前缀）"""

    @property
    @abstractmethod
    def module_title(self) -> str:
        """模块显示名（Pages 导航与帮助信息中使用）"""

    @property
    def module_icon(self) -> str:
        """模块图标（Pages 导航中使用）"""
        return ""

    @property
    def module_desc(self) -> str:
        """模块一句话描述"""
        return ""

    # ══════════════════════════════════════════
    #  能力声明（子类按需覆盖）
    # ══════════════════════════════════════════

    @property
    def supports_accounts(self) -> bool:
        """是否管理多账号（决定 Pages 是否渲染账号列表）"""
        return False

    @property
    def supports_template(self) -> bool:
        """是否支持消息模板（决定 Pages 是否渲染模板编辑器）"""
        return False

    @property
    def supports_query(self) -> bool:
        """是否提供查询能力"""
        return False

    @property
    def supports_login(self) -> bool:
        """是否支持在 Pages 中登录（决定是否显示「登录」按钮）"""
        return False

    @property
    def supports_test(self) -> bool:
        """是否支持在 Pages 中测试凭据（决定是否显示「测试」按钮）"""
        return False

    @property
    def account_file_prefix(self) -> str:
        """账号配置文件名前缀（子类可覆盖，如 "mimo_"）"""
        return ""

    # ══════════════════════════════════════════
    #  注册中心
    # ══════════════════════════════════════════

    def set_context(self, context: Any) -> None:
        """注入 AstrBot 上下文（子类按需使用）

        Args:
            context: AstrBot 的 Context 实例。
        """
        self._context = context

    def set_registry(self, registry: ModuleRegistry | None) -> None:
        """绑定所属注册中心

        Args:
            registry: 注册中心实例；传 None 表示解绑。
        """
        self._registry = registry

    def get_other_module(self, module_name: str) -> ModuleBase | None:
        """获取其他模块实例

        Args:
            module_name: 目标模块名称。

        Returns:
            目标模块实例；不存在时返回 None。
        """
        if self._registry:
            return self._registry.get_module(module_name)
        return None

    # ══════════════════════════════════════════
    #  路径
    # ══════════════════════════════════════════

    def get_config_path(self) -> Path:
        """获取本模块的配置目录（不存在时自动创建）

        Returns:
            形如 `<数据目录>/plugin_data/<插件>/config/<模块>/` 的路径。
        """
        return get_platform_path(self._plugin_name, self.module_name)

    # ══════════════════════════════════════════
    #  模块配置（Pages 管理）
    # ══════════════════════════════════════════

    def get_default_config(self) -> dict:
        """模块默认配置（子类覆盖）

        Returns:
            配置项默认值字典。
        """
        return {}

    def get_config_fields(self) -> list[dict]:
        """模块配置的字段定义（子类覆盖）

        Returns:
            字段列表，每项形如：
            {"key": "proxy", "label": "更新代理", "type": "text",
             "hint": "留空禁用代理", "default": ""}
            支持的 type：text、password、int、bool。
        """
        return []

    def load_module_config(self) -> dict:
        """读取模块配置（默认值与已保存值合并）

        Returns:
            合并后的配置字典。
        """
        config = dict(self.get_default_config())
        saved = load_json_file(self.get_config_path() / MODULE_CONFIG_FILE)
        if saved:
            config.update(saved)
        return config

    def save_module_config(self, config: dict) -> bool:
        """保存模块配置

        Args:
            config: 要保存的配置字典。

        Returns:
            是否保存成功。
        """
        return save_json_file(self.get_config_path() / MODULE_CONFIG_FILE, config)

    # ══════════════════════════════════════════
    #  账号管理（supports_accounts 为 True 时实现）
    # ══════════════════════════════════════════

    def get_account_fields(self) -> list[dict]:
        """账号表单的字段定义（子类覆盖）

        Returns:
            字段列表，格式同 get_config_fields；
            每项可用 `group` 键（字符串或字符串列表）把字段归入某个分组，
            未指定 group 的字段始终显示在账号配置顶部。
        """
        return []

    def get_account_groups(self) -> list[dict]:
        """账号字段的分组定义（子类覆盖）

        Returns:
            分组列表，每项形如：
            {"key": "password", "label": "账号密码登录", "mode": "tab",
             "hint": "说明文字", "resettable": False}

            mode 为 "tab" 时渲染为标签页，为 "inline" 时渲染为账号配置内的
            独立区块；resettable 为 True 的区块会显示「恢复默认」按钮。
            返回空列表表示字段平铺显示，不做分组。
        """
        return []

    def get_accounts(self) -> list[dict]:
        """读取本模块全部账号

        每项额外携带 `_filename` 内部字段，供稳定删除使用。

        Returns:
            账号配置列表。
        """
        config_path = self.get_config_path()
        accounts: list[dict] = []

        for json_file in sorted(config_path.glob("*.json")):
            if json_file.name in RESERVED_FILES:
                continue
            acc = load_json_file(json_file)
            if not acc:
                continue
            acc["_filename"] = json_file.name
            accounts.append(acc)

        return accounts

    def save_accounts(self, accounts: list[dict]) -> bool:
        """保存账号列表

        以文件名为单位增量写入，本次未提交的账号文件会被删除；
        同名账号自动追加序号，避免互相覆盖。

        Args:
            accounts: 账号配置列表。

        Returns:
            是否全部写入成功。
        """
        config_path = self.get_config_path()
        filenames = self._resolve_filenames(accounts)
        ok = True

        for acc, filename in zip(accounts, filenames):
            payload = {k: v for k, v in acc.items() if not k.startswith("_")}
            if not save_json_file(config_path / filename, payload):
                ok = False

        # 清理本次未提交的账号文件
        keep = set(filenames) | RESERVED_FILES
        for old_file in config_path.glob("*.json"):
            if old_file.name not in keep:
                old_file.unlink(missing_ok=True)

        return ok

    def delete_account(self, filename: str) -> dict | None:
        """按文件名删除账号

        Args:
            filename: 账号配置文件名（来自 get_accounts 的 `_filename`）。

        Returns:
            被删除的账号数据；文件不存在时返回 None。
        """
        # 只接受纯文件名，防止路径穿越
        if not filename or Path(filename).name != filename:
            return None

        target = self.get_config_path() / filename
        if not target.exists():
            return None

        deleted = load_json_file(target) or {}
        deleted["_filename"] = filename

        try:
            target.unlink()
        except OSError:
            return None

        return deleted

    def _resolve_filenames(self, accounts: list[dict]) -> list[str]:
        """为账号列表分配唯一文件名

        已有文件名的账号沿用原名，避免改名导致数据搬迁；
        新账号按名称生成，冲突时追加序号。

        Args:
            accounts: 账号配置列表。

        Returns:
            与 accounts 等长的文件名列表。
        """
        used: set[str] = set()
        filenames: list[str] = []

        for acc in accounts:
            name = str(acc.get("_filename") or "").strip()
            if not name or name in used or name in RESERVED_FILES:
                name = get_account_filename(acc, self.account_file_prefix)

            if name in used:
                stem, _, suffix = name.rpartition(".")
                index = 2
                while f"{stem}_{index}.{suffix}" in used:
                    index += 1
                name = f"{stem}_{index}.{suffix}"

            used.add(name)
            filenames.append(name)

        return filenames

    # ══════════════════════════════════════════
    #  模板（supports_template 为 True 时实现）
    # ══════════════════════════════════════════

    def get_default_template(self) -> str:
        """默认消息模板（子类覆盖）

        Returns:
            默认模板文本。
        """
        return ""

    def get_account_template(self, acc: dict) -> str:
        """获取账号使用的模板

        Args:
            acc: 账号配置。

        Returns:
            账号自定义模板；未配置时返回模块默认模板。
        """
        template = str(acc.get("template") or "").strip()
        return template or self.get_default_template()

    def get_var_definitions(self) -> dict[str, str]:
        """模板变量名到中文描述的映射（子类覆盖）

        Returns:
            形如 {"balance": "余额"} 的字典，供 Pages 变量面板展示。
        """
        return {}

    # ══════════════════════════════════════════
    #  查询（supports_query 为 True 时实现）
    # ══════════════════════════════════════════

    async def query(self, account: dict) -> dict:
        """查询单个账号（子类覆盖）

        Args:
            account: 账号配置。

        Returns:
            统一结果字典，包含 success / account_name / data / error / template。
        """
        raise NotImplementedError(f"{self.module_name} 未实现查询能力")

    async def query_all(self) -> list[dict]:
        """查询本模块全部账号

        Returns:
            查询结果列表；单个账号异常不会中断其余账号。
        """
        results: list[dict] = []

        for acc in self.get_accounts():
            label = acc.get("name") or acc.get("account") or acc.get("phone") or "未命名"
            try:
                results.append(await self.query(acc))
            except Exception as e:
                results.append({
                    "success": False,
                    "account_name": label,
                    "error": f"{type(e).__name__}: {e}",
                })

        return results

    def get_result_class(self):
        """本模块使用的查询结果类（子类覆盖）

        Returns:
            QueryResult 子类；返回 None 表示使用默认文本输出。
        """
        return None

    def render(self, result: dict) -> str:
        """把 query() 的返回值渲染为可直接发送的文本

        Args:
            result: query() 的返回值。

        Returns:
            渲染后的文本。
        """
        label = result.get("account_name") or self.module_title

        if not result.get("success"):
            return f"{label}\n❌ {result.get('error') or '查询失败'}"

        result_cls = self.get_result_class()
        if result_cls is None:
            return f"{label}\n✅ 查询成功"

        return result_cls(
            success=True,
            account_name=label,
            data=result.get("data", {}),
            template=result.get("template"),
        ).to_text()

    # ══════════════════════════════════════════
    #  指令（子类按需覆盖）
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        """本模块提供的指令列表（子类覆盖）

        Returns:
            每项形如 {"name": "mimo", "desc": "MiMo 查询指令"}。
        """
        return []

    async def handle_command(self, command: str, args: list[str], event: Any):
        """处理指令（子类覆盖，异步生成器）

        Args:
            command: 指令名称。
            args: 指令参数列表。
            event: AstrBot 消息事件。

        Yields:
            可直接发送的消息结果。
        """
        yield event.plain_result(f"❌ 模块「{self.module_title}」不支持指令 /{command}")

    # ══════════════════════════════════════════
    #  Pages 支持
    # ══════════════════════════════════════════

    def get_web_apis(self) -> list[dict]:
        """本模块提供的 Pages 接口（子类覆盖）

        Returns:
            每项形如 {"path": "config", "handler": fn,
                     "methods": ["GET"], "desc": "..."}；
            path 不含插件名前缀。
        """
        return []

    def get_page_schema(self) -> dict:
        """Pages 渲染所需的模块描述

        前端依据此 schema 通用渲染配置页，因此新增模块通常无需改动前端。

        Returns:
            模块元信息、能力开关与表单字段定义。
        """
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
            "config_fields": self.get_config_fields(),
            "account_fields": self.get_account_fields(),
            "account_groups": self.get_account_groups(),
            "variables": self.get_var_definitions(),
            "default_template": self.get_default_template() if self.supports_template else "",
        }
