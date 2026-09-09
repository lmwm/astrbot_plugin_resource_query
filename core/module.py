"""模块基类

所有功能模块必须继承此基类，并实现必要的抽象方法。

设计原则：
1. 模块自治：每个模块管理自己的配置、查询、下载等
2. 模块隔离：模块之间互不干扰，通过总管理模块通信
3. 统一接口：所有模块提供统一的接口供总管理模块调用
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .registry import ModuleRegistry


class ModuleBase(ABC):
    """模块基类

    所有功能模块必须继承此基类，并实现必要的抽象方法。

    Attributes:
        module_name: 模块名称（如 "mimo", "wasu", "jm"）
        module_icon: 模块图标（用于显示）
        module_desc: 模块描述
    """

    def __init__(self, plugin_dir: Path, plugin_name: str):
        """初始化模块

        Args:
            plugin_dir: 插件目录路径
            plugin_name: 插件名称
        """
        self._plugin_dir = plugin_dir
        self._plugin_name = plugin_name
        self._registry: ModuleRegistry | None = None

    @property
    @abstractmethod
    def module_name(self) -> str:
        """模块名称（必须唯一）"""
        pass

    @property
    @abstractmethod
    def module_icon(self) -> str:
        """模块图标"""
        pass

    @property
    def module_desc(self) -> str:
        """模块描述"""
        return ""

    def set_registry(self, registry: "ModuleRegistry") -> None:
        """设置模块注册中心

        Args:
            registry: 模块注册中心实例
        """
        self._registry = registry

    def get_other_module(self, module_name: str) -> "ModuleBase | None":
        """获取其他模块实例

        通过注册中心获取其他模块，用于模块间通信。

        Args:
            module_name: 目标模块名称

        Returns:
            目标模块实例，如果不存在则返回 None
        """
        if self._registry:
            return self._registry.get_module(module_name)
        return None

    # ══════════════════════════════════════════
    #  配置管理（模块自治）
    # ══════════════════════════════════════════

    def get_config_path(self) -> Path:
        """获取模块配置目录

        Returns:
            模块配置目录路径
        """
        from ..common.utils import get_platform_path
        return get_platform_path(self._plugin_name, self.module_name)

    def load_config(self, filename: str = "config.json") -> dict:
        """加载模块配置

        Args:
            filename: 配置文件名

        Returns:
            配置字典
        """
        config_file = self.get_config_path() / filename
        if config_file.exists():
            try:
                import json
                return json.loads(config_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def save_config(self, config: dict, filename: str = "config.json") -> bool:
        """保存模块配置

        Args:
            config: 配置字典
            filename: 配置文件名

        Returns:
            是否保存成功
        """
        config_file = self.get_config_path() / filename
        try:
            import json
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(
                json.dumps(config, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            return True
        except OSError:
            return False

    # ══════════════════════════════════════════
    #  账号管理（模块自治）
    # ══════════════════════════════════════════

    def get_accounts(self) -> list[dict]:
        """获取该模块的所有账号

        Returns:
            账号配置列表
        """
        from ..common.utils import load_json_file
        accounts = []
        config_path = self.get_config_path()

        if not config_path.exists():
            return accounts

        for json_file in config_path.glob("*.json"):
            # 跳过配置文件
            if json_file.name in ("config.json", "var_config.json"):
                continue
            acc = load_json_file(json_file)
            if acc and isinstance(acc, dict):
                acc["platform"] = self.module_name
                acc["_config_file"] = json_file.name
                accounts.append(acc)

        return accounts

    def save_accounts(self, accounts: list[dict]) -> bool:
        """保存该模块的所有账号

        Args:
            accounts: 账号配置列表

        Returns:
            是否保存成功
        """
        from ..common.utils import save_json_file, save_text_file
        config_path = self.get_config_path()
        config_path.mkdir(parents=True, exist_ok=True)

        # 收集当前文件名
        existing_files = set()
        for acc in accounts:
            filename = self._get_account_filename(acc)
            filepath = config_path / filename

            # 保存账号配置（移除内部字段）
            save_acc = {
                k: v for k, v in acc.items()
                if not k.startswith("_") and k != "template" and k != "platform"
            }
            save_json_file(filepath, save_acc)
            existing_files.add(filename)

            # 保存模板文件
            template = acc.get("template", "")
            if template:
                template_file = filepath.with_suffix(".txt")
                save_text_file(template_file, template)

        # 删除不在列表中的旧文件
        for old_file in config_path.glob("*.json"):
            if old_file.name in ("config.json", "var_config.json"):
                continue
            if old_file.name not in existing_files:
                old_file.unlink(missing_ok=True)
                template_file = old_file.with_suffix(".txt")
                if template_file.exists():
                    template_file.unlink(missing_ok=True)

        return True

    def delete_account(self, index: int) -> dict | None:
        """删除指定索引的账号

        Args:
            index: 账号索引（从 0 开始）

        Returns:
            被删除的账号，如果索引无效则返回 None
        """
        accounts = self.get_accounts()
        if index < 0 or index >= len(accounts):
            return None

        deleted = accounts.pop(index)
        self.save_accounts(accounts)
        return deleted

    def _get_account_filename(self, acc: dict) -> str:
        """获取账号配置文件名

        Args:
            acc: 账号配置

        Returns:
            文件名
        """
        name = acc.get("name", "").strip()
        if not name:
            name = acc.get("account") or acc.get("phone") or "unnamed"
        # 清理文件名中的非法字符
        name = "".join(c for c in name if c.isalnum() or c in "-_\u4e00-\u9fff")
        if not name:
            name = "unnamed"
        return f"{name}.json"

    # ══════════════════════════════════════════
    #  模板管理（模块自治）
    # ══════════════════════════════════════════

    def get_default_template(self) -> str:
        """获取默认模板

        子类可以覆盖此方法以提供自定义的默认模板加载逻辑。

        Returns:
            默认模板内容
        """
        # 尝试从 templates 目录加载
        template_file = self._plugin_dir / "templates" / f"{self.module_name}_default.txt"
        if template_file.exists():
            try:
                return template_file.read_text(encoding="utf-8")
            except OSError:
                pass
        return ""

    def get_account_template(self, acc: dict) -> str:
        """获取账号的模板

        Args:
            acc: 账号配置

        Returns:
            模板内容
        """
        # 优先使用账号自定义模板
        if acc.get("template"):
            return acc["template"]

        # 尝试从模板文件加载
        config_path = self.get_config_path()
        filename = self._get_account_filename(acc)
        template_file = config_path / filename.replace(".json", ".txt")
        if template_file.exists():
            try:
                return template_file.read_text(encoding="utf-8")
            except OSError:
                pass

        # 使用默认模板
        return self.get_default_template()

    # ══════════════════════════════════════════
    #  查询接口（子类实现）
    # ══════════════════════════════════════════

    @abstractmethod
    async def query(self, account: dict) -> dict:
        """查询单个账号

        Args:
            account: 账号配置

        Returns:
            查询结果字典，包含以下字段：
            - success: bool, 是否成功
            - data: dict, 查询数据（成功时）
            - error: str, 错误信息（失败时）
            - account_name: str, 账号名称
        """
        pass

    async def query_all(self) -> list[dict]:
        """查询该模块的所有账号

        Returns:
            查询结果列表
        """
        results = []
        accounts = self.get_accounts()

        for acc in accounts:
            try:
                result = await self.query(acc)
                results.append(result)
            except Exception as e:
                results.append({
                    "success": False,
                    "account_name": acc.get("name", "未知"),
                    "error": str(e)
                })

        return results

    # ══════════════════════════════════════════
    #  Web API 支持（子类可选实现）
    # ══════════════════════════════════════════

    def get_web_apis(self) -> list[dict]:
        """获取该模块提供的 Web API 列表

        Returns:
            API 定义列表，每个 API 包含：
            - path: str, API 路径（不含模块前缀）
            - handler: Callable, 处理函数
            - methods: list[str], HTTP 方法
            - desc: str, API 描述
        """
        return []

    # ══════════════════════════════════════════
    #  指令支持（子类可选实现）
    # ══════════════════════════════════════════

    def get_commands(self) -> list[dict]:
        """获取该模块提供的指令列表

        Returns:
            指令定义列表，每个指令包含：
            - name: str, 指令名称
            - desc: str, 指令描述
            - handler: str, 处理方法名
        """
        return []

    async def handle_command(self, command: str, args: list[str], event: Any) -> Any:
        """处理指令

        Args:
            command: 指令名称
            args: 指令参数
            event: AstrBot 事件对象

        Returns:
            处理结果（生成器）
        """
        # 默认实现：返回未实现提示
        yield f"❌ 模块 {self.module_name} 未实现指令 {command}"
