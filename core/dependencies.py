# 插件级依赖检测与补装
#
# 各模块用 required_packages 声明依赖（导入名 → 安装名），插件初始化时统一检查；
# 缺任何一个就按插件根 requirements.txt 调用 AstrBot 自带的 pip_installer 补装一次。
#
# 为什么要自己做：AstrBot 只在安装插件、它自己的插件更新、失败插件恢复、
# 插件导入抛 ModuleNotFoundError 时装依赖；普通重载与插件自更新都不触发。
# 探测会真实导入一次，能发现缺传递依赖或装坏的包；结果按进程缓存。

from __future__ import annotations

import importlib
import importlib.util

from ..common.module_log import module_logger

logger = module_logger("core")

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
    # 缺依赖时补装一次；返回（补装前缺失的安装名, 是否齐全, 剩余缺失或失败原因）
    missing_names = missing(required)
    if not missing_names:
        return [], True, ""

    logger.warning(
        f"缺少运行依赖：{'、'.join(missing_names)}"
        f"（模块 {'、'.join(missing_modules(required))}），开始补装"
    )

    ok, detail = await install(requirements_path)
    if not ok:
        return missing_names, False, detail

    remaining = missing(required)
    if remaining:
        return missing_names, False, "、".join(remaining)
    return missing_names, True, ""