# 账号存储：以文件为单位的账号读取、写入与删除
#
# 账号文件名优先沿用已有 `_filename`（避免改名导致数据搬迁），
# 新账号按名称生成，冲突时追加序号。

from __future__ import annotations

from pathlib import Path

from ..common.utils import get_account_filename, load_json_file, save_json_file

# 配置目录中非账号的保留文件
RESERVED_FILES = {"config.json", "var_config.json"}


class AccountStore:
    # 某个模块配置目录下的账号集合

    def __init__(self, config_path: Path, file_prefix: str = "") -> None:
        self._config_path = Path(config_path)
        self._file_prefix = file_prefix

    def list(self) -> list[dict]:
        # 读取全部账号；每项额外携带 `_filename` 供稳定删除
        accounts: list[dict] = []

        for json_file in sorted(self._config_path.glob("*.json")):
            if json_file.name in RESERVED_FILES:
                continue
            account = load_json_file(json_file)
            if not account:
                continue
            account["_filename"] = json_file.name
            accounts.append(account)

        return accounts

    def save(self, accounts: list[dict]) -> bool:
        # 增量写入；本次未提交的账号文件会被删除
        filenames = self._resolve_filenames(accounts)
        ok = True

        for account, filename in zip(accounts, filenames):
            payload = {k: v for k, v in account.items() if not k.startswith("_")}
            if not save_json_file(self._config_path / filename, payload):
                ok = False

        keep = set(filenames) | RESERVED_FILES
        for old_file in self._config_path.glob("*.json"):
            if old_file.name not in keep:
                old_file.unlink(missing_ok=True)

        return ok

    def delete(self, filename: str) -> dict | None:
        # 按文件名删除；只接受纯文件名，防止路径穿越
        if not filename or Path(filename).name != filename:
            return None

        target = self._config_path / filename
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
        # 为账号列表分配唯一文件名
        used: set[str] = set()
        filenames: list[str] = []

        for account in accounts:
            name = str(account.get("_filename") or "").strip()
            if not name or name in used or name in RESERVED_FILES:
                name = get_account_filename(account, self._file_prefix)

            if name in used:
                stem, _, suffix = name.rpartition(".")
                index = 2
                while f"{stem}_{index}.{suffix}" in used:
                    index += 1
                name = f"{stem}_{index}.{suffix}"

            used.add(name)
            filenames.append(name)

        return filenames
