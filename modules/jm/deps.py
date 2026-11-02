# JM 运行依赖检测
#
# 插件更新或换机后，jmcomic、img2pdf 等依赖可能没装上（pip 安装失败、site-packages 被清），
# 或装了但缺少传递依赖（如 jmcomic 缺 Crypto）。这里做只读探测，把缺失项交给模块写日志、
# 按配置模板提示，避免异常直接冒到聊天或插件加载期。

from __future__ import annotations

import importlib
import importlib.util

from ...common.module_log import module_logger

logger = module_logger("jm")

# 导入名 → 安装名（提示用户时用安装名）
REQUIRED_PACKAGES = {
    "jmcomic": "jmcomic",
    "img2pdf": "img2pdf",
    "PIL": "Pillow",
}

# 探测结果缓存：依赖在运行期不变，装好后需要重载插件才失效
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


def is_available(module_name: str) -> bool:
    return _probe(module_name)


def missing_modules() -> list[str]:
    # 缺失依赖的导入名，供日志定位
    return [name for name in REQUIRED_PACKAGES if not is_available(name)]


def missing() -> list[str]:
    # 缺失依赖的安装名（如 PIL → Pillow），供用户提示
    return [REQUIRED_PACKAGES[name] for name in missing_modules()]