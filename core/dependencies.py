# 插件级依赖检测与补装
#
# 各模块用 required_packages 声明依赖（导入名 → 安装名），插件初始化时统一检查；
# 缺任何一个、或 requirements.txt 里用 `==` 锁定的版本与已装版本不一致，就按插件根
# requirements.txt 调用 AstrBot 自带的 pip_installer 补装一次。
#
# 为什么要自己做：AstrBot 只在安装插件、它自己的插件更新、失败插件恢复、
# 插件导入抛 ModuleNotFoundError 时装依赖；普通重载与插件自更新都不触发。
# 为什么要查版本：pip 的 `--upgrade-strategy only-if-needed` 不会升级已满足
# 下限约束的包，`jmcomic>=2.7.0` 这类写法会一直停在首次安装的旧版本。
# 探测会真实导入一次，能发现缺传递依赖或装坏的包；结果按进程缓存。

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import re
from pathlib import Path

from ..common.module_log import module_logger

logger = module_logger("core")

# requirements.txt 里的精确锁定行，例如 `jmcomic==2.7.10`
_PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*==\s*([^;,\s#]+)")

# 探测结果缓存：装好后需要 clear_cache() 才会重新探测
_PROBE_CACHE: dict[str, bool] = {}


def _probe(module_name: str) -> bool:
    # 先查可寻址再真导入一次：安装损坏、缺传递依赖也能发现
    if module_name in _PROBE_CACHE:
        return _PROBE_CACHE[module_name]

    available = False
    try:
        if importlib.util.find_spec(module_name) is not None:
            importlib.import_module(module_name)
            available = True
    except (ImportError, OSError, ValueError, AttributeError) as e:
        logger.warning(f"依赖 {module_name} 不可用：{type(e).__name__}: {e}")

    _PROBE_CACHE[module_name] = available
    return available


def collect_required(modules) -> dict[str, str]:
    # 汇总各模块声明的依赖；后登记的模块覆盖同名项
    required: dict[str, str] = {}
    for module in modules:
        required.update(module.required_packages)
    return required


def missing_modules(required: dict[str, str]) -> list[str]:
    # 缺失依赖的导入名，供日志定位
    return [name for name in required if not _probe(name)]


def missing(required: dict[str, str]) -> list[str]:
    # 缺失依赖的安装名（如 PIL → Pillow），供用户提示
    return [required[name] for name in missing_modules(required)]


def clear_cache() -> None:
    # 补装或手动安装后清缓存，让下次探测重新导入
    _PROBE_CACHE.clear()


def pinned_versions(requirements_path: str) -> dict[str, str]:
    # 读取 requirements.txt 里的 `==` 锁定项；返回 安装名（小写）→ 版本
    try:
        text = Path(requirements_path).read_text(encoding="utf-8")
    except OSError:
        return {}

    pins: dict[str, str] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        match = _PIN_RE.match(line)
        if match:
            pins[match.group(1).lower()] = match.group(2)
    return pins


def _installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def version_conflicts(pins: dict[str, str]) -> list[tuple[str, str, str]]:
    # 已装版本与锁定版本不一致（含未安装）；返回（安装名, 需要版本, 实际版本）
    conflicts: list[tuple[str, str, str]] = []
    for name, pinned in pins.items():
        actual = _installed_version(name)
        if actual != pinned:
            conflicts.append((name, pinned, actual or "未安装"))
    return conflicts


def _describe_conflicts(conflicts: list[tuple[str, str, str]]) -> list[str]:
    return [
        f"{name} 需要 {pinned}，当前 {actual}"
        for name, pinned, actual in conflicts
    ]


async def install(requirements_path: str) -> tuple[bool, str]:
    # 复用 AstrBot 自带的安装器按插件 requirements.txt 补装；返回（是否成功, 失败原因）
    from astrbot.core import pip_installer

    try:
        await pip_installer.install(requirements_path=requirements_path)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"

    clear_cache()
    return True, ""


async def ensure(
    required: dict[str, str], requirements_path: str
) -> tuple[list[str], bool, str]:
    # 缺依赖或版本不符时补装一次；返回（需处理的项, 是否齐全, 剩余缺失或失败原因）
    pins = pinned_versions(requirements_path)
    missing_names = missing(required)
    missing_set = {name.lower() for name in missing_names}

    # 已缺失的包装不上时会在 missing 里体现，这里不重复报版本
    conflicts = [
        item for item in version_conflicts(pins) if item[0] not in missing_set
    ]
    if not missing_names and not conflicts:
        return [], True, ""

    problems = [*missing_names, *_describe_conflicts(conflicts)]
    logger.warning(f"依赖需要处理：{'、'.join(problems)}，开始补装")

    ok, detail = await install(requirements_path)
    if not ok:
        return problems, False, detail

    remaining_missing = missing(required)
    remaining_set = {name.lower() for name in remaining_missing}
    remaining_conflicts = [
        item
        for item in version_conflicts(pins)
        if item[0] not in remaining_set
    ]
    if remaining_missing or remaining_conflicts:
        return (
            problems,
            False,
            "、".join([*remaining_missing, *_describe_conflicts(remaining_conflicts)]),
        )
    return problems, True, ""
