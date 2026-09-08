"""JMComic 下载管理器

负责管理 JMComic 漫画的下载、PDF 转换和缓存。

架构设计：
  JMManager（管理器）
    ├── Downloader（下载器）
    ├── PDFConverter（PDF转换器）
    └── CacheManager（缓存管理器）
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Callable, Optional

from .models import AlbumInfo, DownloadResult, ProgressCallback, ProgressInfo


class JMManager:
    """JMComic 下载管理器

    负责管理 JMComic 漫画的下载、PDF 转换和缓存。
    """

    def __init__(self, config: dict, download_dir: str):
        """初始化管理器

        Args:
            config: 配置字典
            download_dir: 下载目录路径
        """
        self._config = config
        self._download_dir = Path(download_dir)
        self._download_dir.mkdir(parents=True, exist_ok=True)

        # 缓存目录
        self._cache_dir = self._download_dir / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # 就绪目录（PDF 文件）
        self._ready_dir = self._download_dir / "ready"
        self._ready_dir.mkdir(parents=True, exist_ok=True)

    def update_config(self, config: dict) -> None:
        """更新配置

        Args:
            config: 新的配置字典
        """
        self._config = config

    def check_local(self, album_id: str) -> dict | None:
        """检查本地是否有已下载的内容

        Args:
            album_id: 漫画 ID

        Returns:
            如果本地有内容，返回包含信息的字典，否则返回 None
        """
        album_dir = self._cache_dir / str(album_id)
        info_file = album_dir / "info.json"

        # 检查是否有 PDF 文件
        pdf_files = list(self._ready_dir.glob(f"JM{album_id}-*.pdf"))
        if pdf_files:
            pdf_path = pdf_files[0]
            pdf_size_mb = pdf_path.stat().st_size / (1024 * 1024)
            return {
                "has_pdf": True,
                "pdf_path": str(pdf_path),
                "pdf_name": pdf_path.name,
                "pdf_size_mb": round(pdf_size_mb, 2),
                "album_id": album_id,
            }

        # 检查是否有缓存的图片目录
        if album_dir.exists() and info_file.exists():
            try:
                info = json.loads(info_file.read_text(encoding="utf-8"))
                image_files = list(album_dir.glob("*.jpg")) + list(album_dir.glob("*.png"))
                return {
                    "has_pdf": False,
                    "has_images": len(image_files) > 0,
                    "image_count": len(image_files),
                    "album_id": album_id,
                    "info": info,
                }
            except (json.JSONDecodeError, OSError):
                pass

        return None

    async def get_album_info(self, album_id: str) -> AlbumInfo:
        """获取漫画信息

        Args:
            album_id: 漫画 ID

        Returns:
            AlbumInfo 对象
        """
        # 检查本地缓存
        album_dir = self._cache_dir / str(album_id)
        info_file = album_dir / "info.json"

        if info_file.exists():
            try:
                data = json.loads(info_file.read_text(encoding="utf-8"))
                return AlbumInfo(
                    id=str(data.get("id", album_id)),
                    name=data.get("name", "未知"),
                    author=data.get("author", "未知"),
                    chapter_count=data.get("chapter_count", 0),
                    image_count=data.get("image_count", 0),
                    tags=data.get("tags", []),
                )
            except (json.JSONDecodeError, OSError):
                pass

        # 从网络获取信息
        try:
            import jmcomic
            album = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: jmcomic.get_album_detail(str(album_id))
            )

            # 保存信息到本地
            album_dir.mkdir(parents=True, exist_ok=True)
            info = {
                "id": album_id,
                "name": album.title if hasattr(album, 'title') else "未知",
                "author": album.author if hasattr(album, 'author') else "未知",
                "chapter_count": len(album.episode_list) if hasattr(album, 'episode_list') else 0,
                "image_count": sum(len(ep.image_list) for ep in album.episode_list) if hasattr(album, 'episode_list') else 0,
                "tags": [],
            }
            info_file.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

            return AlbumInfo(
                id=str(album_id),
                name=info["name"],
                author=info["author"],
                chapter_count=info["chapter_count"],
                image_count=info["image_count"],
                tags=info["tags"],
            )
        except ImportError:
            return AlbumInfo(id=str(album_id), name="未知（jmcomic 未安装）")
        except Exception as e:
            return AlbumInfo(id=str(album_id), name=f"获取失败: {e}")

    async def download(
        self,
        album_id: str,
        progress_callback: Optional[ProgressCallback] = None,
        force_redownload: bool = False,
    ) -> DownloadResult:
        """下载漫画并生成 PDF

        Args:
            album_id: 漫画 ID
            progress_callback: 进度回调函数
            force_redownload: 是否强制重新下载

        Returns:
            DownloadResult 对象
        """
        try:
            import jmcomic
            from img2pdf import convert as img2pdf_convert
        except ImportError as e:
            return DownloadResult(
                success=False,
                message=f"缺少依赖: {e}",
                album_id=album_id,
            )

        # 检查本地缓存
        if not force_redownload:
            local = self.check_local(album_id)
            if local and local.get("has_pdf"):
                return DownloadResult(
                    success=True,
                    message="使用本地缓存",
                    album_id=album_id,
                    pdf_path=local.get("pdf_path"),
                    pdf_name=local.get("pdf_name"),
                    file_size_mb=local.get("pdf_size_mb", 0),
                    from_cache=True,
                )

        # 获取漫画信息
        album_info = await self.get_album_info(album_id)

        # 报告进度
        if progress_callback:
            progress_callback(ProgressInfo(current=0, total=100, message="开始下载..."))

        try:
            # 下载图片
            album_dir = self._cache_dir / str(album_id)
            album_dir.mkdir(parents=True, exist_ok=True)

            # 使用 jmcomic 下载
            def _download():
                option = jmcomic.JmOption.default()
                client = option.new_jm_client()
                album = client.get_album_detail(str(album_id))

                image_list = []
                for ep in album.episode_list:
                    for img in ep.image_list:
                        image_list.append(img)

                total = len(image_list)
                downloaded = []

                for i, img in enumerate(image_list):
                    try:
                        img_data = client.get_photo_detail(img.photo_id, img.img_id)
                        img_path = album_dir / f"{i:04d}.jpg"
                        if not img_path.exists():
                            img_path.write_bytes(img_data.img_data)
                        downloaded.append(str(img_path))

                        if progress_callback:
                            progress_callback(ProgressInfo(
                                current=i + 1,
                                total=total,
                                message=f"下载中 {i + 1}/{total}"
                            ))
                    except Exception:
                        continue

                return downloaded

            image_paths = await asyncio.get_event_loop().run_in_executor(None, _download)

            if not image_paths:
                return DownloadResult(
                    success=False,
                    message="下载失败：未获取到图片",
                    album_id=album_id,
                    album_info=album_info,
                )

            # 生成 PDF
            if progress_callback:
                progress_callback(ProgressInfo(current=90, total=100, message="生成 PDF..."))

            pdf_name = f"JM{album_id}-{album_info.name[:50]}.pdf"
            pdf_name = "".join(c for c in pdf_name if c.isalnum() or c in "-_. ")
            pdf_path = self._ready_dir / pdf_name

            with open(pdf_path, "wb") as f:
                f.write(img2pdf_convert(image_paths))

            file_size_mb = pdf_path.stat().st_size / (1024 * 1024)

            if progress_callback:
                progress_callback(ProgressInfo(current=100, total=100, message="完成"))

            return DownloadResult(
                success=True,
                message="下载完成",
                album_id=album_id,
                album_name=album_info.name,
                album_info=album_info,
                pdf_path=str(pdf_path),
                pdf_name=pdf_name,
                file_size_mb=round(file_size_mb, 2),
                image_count=len(image_paths),
            )

        except Exception as e:
            return DownloadResult(
                success=False,
                message=f"下载失败: {e}",
                album_id=album_id,
                album_info=album_info,
            )

    def cleanup_files(self, album_id: str) -> None:
        """清理指定漫画的所有下载文件

        Args:
            album_id: 漫画 ID
        """
        # 清理缓存目录
        album_dir = self._cache_dir / str(album_id)
        if album_dir.exists():
            shutil.rmtree(album_dir, ignore_errors=True)

        # 清理 PDF 文件
        for pdf_file in self._ready_dir.glob(f"JM{album_id}-*.pdf"):
            pdf_file.unlink(missing_ok=True)
