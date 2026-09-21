"""功能模块层

每个功能一个独立模块，全部继承 `core.module.ModuleBase`：
- mimo：小米 MiMo 用量查询
- wasu：华数广电流量 / 话费查询
- jm：JMComic 漫画下载
- update：插件自身更新

新增模块只需在此目录新建包，并在 `main.py` 的模块清单中登记一行。
"""

from .jm import JMModule
from .mimo import MimoModule
from .update import UpdateModule
from .wasu import WasuModule

__all__ = [
    "MimoModule",
    "WasuModule",
    "JMModule",
    "UpdateModule",
]
