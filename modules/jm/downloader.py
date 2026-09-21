"""JM 下载适配层

负责加载 / 保存 JM 下载配置、定位下载目录，并把请求转发给
`core` 中的 JMManager。模块层只与本适配层交互。
"""

from __future__ import annotations

from pathlib import Path

from ...common.utils import load_json_file, save_json_file
from .core import JMManager
from .core.models import ProgressCallback
from .utils import get_default_config

# 配置文件名（与模块配置目录中的文件名一致）
CONFIG_FILE = "config.json"


class JMDownloader:
    """JMComic 下载适配层"""

    def __init__(self, config_path: Path) -> None:
        """初始化适配层

        Args:
            config_path: JM 配置目录（如 config/jm/）。
        """
        self._config_path = Path(config_path)
        self._config_path.mkdir(parents=True, exist_ok=True)
        self._config = self.load_config()
        self._manager = self._create_manager()

    def load_config(self) -> dict:
        """加载配置

        默认值来自 `modules/jm/config.yaml`，用户经 Pages 保存的配置优先。

        Returns:
            配置字典。
        """
        config = get_default_config()
        saved = load_json_file(self._config_path / CONFIG_FILE)
        if saved:
            config.update(saved)
        return config

    def save_config(self, config: dict) -> bool:
        """保存配置

        Args:
            config: 配置字典。

        Returns:
            是否保存成功。
        """
        return save_json_file(self._config_path / CONFIG_FILE, config)

    def reload_config(self) -> dict:
        """重新加载配置并同步给下载管理器

        Returns:
            最新的配置字典。
        """
        self._config = self.load_config()
        self._manager.update_config(self._config)
        return self._config

    def _create_manager(self) -> JMManager:
        """创建下载管理器

        Returns:
            JMManager 实例，下载目录位于 AstrBot 数据目录下。
        """
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        return JMManager(
            config=self._config,
            download_dir=str(Path(get_astrbot_data_path()) / "JMDownload"),
        )

    def check_local(self, album_id: str) -> dict | None:
        """检查本地缓存

        Args:
            album_id: 漫画 ID。

        Returns:
            缓存信息字典；无缓存时返回 None。
        """
        return self._manager.check_local(album_id)

    async def get_album_info(self, album_id: str):
        """获取漫画信息

        Args:
            album_id: 漫画 ID。

        Returns:
            AlbumInfo 实例。
        """
        return await self._manager.get_album_info(str(album_id))

    async def download(
        self,
        album_id: str,
        progress_callback: ProgressCallback | None = None,
        force_redownload: bool = False,
    ) -> dict:
        """下载漫画并生成 PDF

        Args:
            album_id: 漫画 ID。
            progress_callback: 进度回调 (current, total, message)。
            force_redownload: 是否忽略缓存强制重新下载。

        Returns:
            下载结果字典。
        """
        result = await self._manager.download(
            album_id=str(album_id),
            progress_callback=progress_callback,
            force_redownload=force_redownload,
        )
        return result.to_dict()
