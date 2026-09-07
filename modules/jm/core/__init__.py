"""JMComic 核心模块

注意：此模块引用原有的 core 模块实现，避免代码重复。
"""

# 引用原有的 core 模块
import sys
from pathlib import Path

# 添加父目录到路径，以便引用原有的 core 模块
_parent_dir = Path(__file__).parent.parent.parent.parent
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

# 引用原有的 core 模块
from jm.core.manager import JMManager
from jm.core.models import DownloadResult, AlbumInfo, ProgressInfo
from jm.core.config import ManagerConfig

__all__ = [
    "JMManager",
    "DownloadResult",
    "AlbumInfo",
    "ProgressInfo",
    "ManagerConfig",
]
