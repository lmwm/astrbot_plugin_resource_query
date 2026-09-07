"""通用账号管理器"""

import json
from pathlib import Path

from .utils import (
    get_account_filename,
    get_config_path,
    get_data_path,
    get_platform_path,
    load_json_file,
    load_text_file,
    save_json_file,
    save_text_file,
)


class AccountManager:
    """通用账号管理器

    提供账号文件的读写、模板文件的读写、账号列表的增删改查等功能。
    """

    def __init__(self, plugin_name: str, plugin_dir: Path):
        """初始化账号管理器

        Args:
            plugin_name: 插件名称。
            plugin_dir: 插件目录路径。
        """
        self._plugin_name = plugin_name
        self._plugin_dir = plugin_dir

    def _get_data_path(self) -> Path:
        """获取插件数据目录"""
        return get_data_path(self._plugin_name)

    def _get_config_path(self) -> Path:
        """获取配置根目录"""
        return get_config_path(self._plugin_name)

    def _get_platform_path(self, platform: str) -> Path:
        """获取指定平台的配置目录"""
        return get_platform_path(self._plugin_name, platform)

    def _get_jm_config_path(self) -> Path:
        """获取 JM 下载配置目录"""
        return get_platform_path(self._plugin_name, "jm")

    def _get_account_filename(self, acc: dict) -> str:
        """获取账号配置文件名"""
        return get_account_filename(acc)

    def get_all_accounts(self) -> list:
        """获取所有账号

        Returns:
            账号配置列表。
        """
        accounts = []
        config_path = self._get_config_path()

        # 遍历所有平台目录
        for platform_dir in config_path.iterdir():
            if not platform_dir.is_dir():
                continue
            platform = platform_dir.name
            # 跳过非平台目录
            if platform not in ("mimo", "wasu"):
                continue

            # 读取该平台下的所有 json 文件（跳过 var_config.json）
            for json_file in platform_dir.glob("*.json"):
                # 跳过变量配置文件
                if json_file.name == "var_config.json":
                    continue
                acc = load_json_file(json_file)
                if acc and isinstance(acc, dict):
                    acc["platform"] = platform
                    acc["_config_file"] = json_file.name
                    acc["_config_dir"] = str(platform_dir)
                    # 读取对应的模板文件
                    template_file = platform_dir / json_file.name.replace(".json", ".txt")
                    template = load_text_file(template_file)
                    if template:
                        acc["template"] = template
                    elif not acc.get("template"):
                        acc["template"] = self._get_default_template(platform)
                    accounts.append(acc)

        # 为没有名称的账号自动填充默认名称并保存
        if self._fill_default_names(accounts):
            self.save_all_accounts(accounts)

        return accounts

    def save_all_accounts(self, accounts: list):
        """保存所有账号到单独的配置文件和模板文件

        Args:
            accounts: 账号配置列表。
        """
        config_path = self._get_config_path()

        # 第零步：为没有名称的账号自动生成默认名称
        self._fill_default_names(accounts)

        # 第一步：按平台分组，收集新账号的文件名（不写入磁盘）
        platform_files: dict[str, set[str]] = {}
        acc_file_pairs: list[tuple[dict, str, str]] = []  # (acc, platform, filename)

        for acc in accounts:
            platform = acc.get("platform", "unknown")
            filename = self._get_account_filename(acc)
            # 处理文件名冲突：追加数字后缀
            if platform not in platform_files:
                platform_files[platform] = set()
            original = filename
            counter = 2
            while filename in platform_files[platform]:
                stem = original.rsplit(".", 1)[0]
                filename = f"{stem}_{counter}.json"
                counter += 1
            platform_files[platform].add(filename)
            acc_file_pairs.append((acc, platform, filename))

        # 第二步：写入所有新文件
        for acc, platform, filename in acc_file_pairs:
            platform_dir = self._get_platform_path(platform)
            filepath = platform_dir / filename
            save_acc = {k: v for k, v in acc.items() if not k.startswith("_") and k != "template" and k != "platform"}
            save_json_file(filepath, save_acc)
            template = acc.get("template", "")
            template_filename = filename.replace(".json", ".txt")
            template_filepath = platform_dir / template_filename
            save_text_file(template_filepath, template)

        # 第三步：删除不在新列表中的旧文件
        for platform_dir in config_path.iterdir():
            if not platform_dir.is_dir():
                continue
            platform = platform_dir.name
            if platform not in platform_files:
                # 该平台已无账号，删除该平台目录下的所有文件
                for old_file in platform_dir.glob("*"):
                    if old_file.is_file():
                        old_file.unlink(missing_ok=True)
                # 删除空平台目录
                if not any(platform_dir.iterdir()):
                    platform_dir.rmdir()
                continue
            valid_filenames = platform_files[platform]
            for old_file in platform_dir.glob("*.json"):
                if old_file.name not in valid_filenames:
                    old_file.unlink(missing_ok=True)
                    template_file = platform_dir / old_file.name.replace(".json", ".txt")
                    if template_file.exists():
                        template_file.unlink(missing_ok=True)
            # 删除空平台目录
            if not any(platform_dir.iterdir()):
                platform_dir.rmdir()

    def _fill_default_names(self, accounts: list) -> bool:
        """为没有名称的账号自动生成默认名称

        所有平台共享同一个序号计数器，最大为 999。

        Args:
            accounts: 账号配置列表（原地修改）。

        Returns:
            是否有账号被修改。
        """
        changed = False

        # 统计所有平台已有的名称（共享序号）
        max_counter = 0
        for acc in accounts:
            name = acc.get("name", "").strip()
            if name and name.startswith("账号"):
                try:
                    num = int(name[2:])
                    max_counter = max(max_counter, num)
                except ValueError:
                    pass

        # 为没有名称的账号生成默认名称（共享序号，最大 999）
        counter = max_counter
        for acc in accounts:
            if not acc.get("name", "").strip():
                counter += 1
                if counter > 999:
                    counter = 1  # 超过 999 后从 001 开始循环
                acc["name"] = f"账号{counter:03d}"
                changed = True

        return changed

    def delete_account(self, platform: str, index: int) -> dict | None:
        """删除指定平台的指定账号

        Args:
            platform: 平台名称（mimo/wasu）。
            index: 账号在该平台列表中的序号（从 0 开始）。

        Returns:
            被删除的账号配置，如果序号无效则返回 None。
        """
        platform_accounts = self.get_accounts_by_platform(platform)
        if index < 0 or index >= len(platform_accounts):
            return None

        deleted_acc = platform_accounts[index]
        all_accounts = self.get_all_accounts()

        # 找到在总列表中的真实索引
        real_idx = self._find_real_index(all_accounts, platform, deleted_acc)
        if real_idx < 0:
            return None

        all_accounts.pop(real_idx)
        self.save_all_accounts(all_accounts)
        return deleted_acc

    def _find_real_index(self, all_accounts: list, platform: str, target: dict) -> int:
        """在总列表中查找目标账号的真实索引

        通过比较文件名来定位账号，文件名是账号的稳定标识。

        Args:
            all_accounts: 所有账号列表。
            platform: 平台名称。
            target: 目标账号配置。

        Returns:
            真实索引，未找到返回 -1。
        """
        target_filename = self._get_account_filename(target)
        for i, acc in enumerate(all_accounts):
            if acc.get("platform") != platform:
                continue
            if self._get_account_filename(acc) == target_filename:
                return i
        return -1

    def _get_default_template(self, platform: str) -> str:
        """获取默认模板内容

        Args:
            platform: 平台名称。

        Returns:
            模板内容。
        """
        template_file = self._plugin_dir / "templates" / f"{platform}_default.txt"
        template = load_text_file(template_file)
        return template or ""

    def get_accounts_by_platform(self, platform: str) -> list:
        """获取指定平台的所有账号

        Args:
            platform: 平台名称。

        Returns:
            该平台的账号列表。
        """
        return [acc for acc in self.get_all_accounts() if acc.get("platform") == platform]

    def get_account_indices(self, platform: str) -> list:
        """获取指定平台账号在总列表中的索引

        Args:
            platform: 平台名称。

        Returns:
            [(index, account), ...] 列表。
        """
        all_accounts = self.get_all_accounts()
        return [(i, acc) for i, acc in enumerate(all_accounts) if acc.get("platform") == platform]

    def find_account_index(self, platform: str, identifier: str, key: str = "account") -> int:
        """查找账号在指定平台列表中的索引

        Args:
            platform: 平台名称。
            identifier: 要查找的标识符。
            key: 要比较的字段名。

        Returns:
            索引，未找到返回 -1。
        """
        platform_accounts = self.get_accounts_by_platform(platform)
        for i, acc in enumerate(platform_accounts):
            if acc.get(key) == identifier:
                return i
        return -1
