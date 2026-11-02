# 图片合成 PDF
#
# 站点原图多为 webp，直接交给 img2pdf 会被无损转码、体积膨胀数倍，
# 因此默认在下载阶段就让 jmcomic 直接存成 JPEG（质量 75），生成 PDF 时
# 直接嵌入、不再二次转码；其它质量值仍下载原图，再逐张转成目标质量的
# JPEG。逐张写临时文件而不是把全部字节留在内存，避免大本子占用过多内存。
#
# 转码用线程池并行（PIL 的编码在 C 层，线程可重叠），PDF 用 outputstream
# 直接写盘；先写同目录临时文件，成功后再原子替换，失败时保留旧 PDF。

from __future__ import annotations

import inspect
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ...common.module_log import module_logger

logger = module_logger("jm")

_TMP_DIR_NAME = "__pdf_tmp__"
_JPEG_SUFFIXES = {".jpg", ".jpeg"}
_MAX_CONVERT_WORKERS = 8


def make_pdf(
    album_root: Path,
    pdf_name: str,
    images: list[Path],
    quality: int,
    direct_jpeg: bool = False,
) -> Path:
    # 生成 PDF 并返回路径；没有可用图片时抛 RuntimeError
    # 依赖在调用时才导入：缺库时让下载返回可读错误，而不是插件加载失败
    from PIL import Image

    quality = max(1, min(95, int(quality)))
    album_root = Path(album_root)
    final_name = Path(str(pdf_name)).name
    final_path = album_root / f"{final_name}.pdf"
    tmp_pdf = album_root / f".{final_name}.pdf.tmp"
    tmp_dir = album_root / _TMP_DIR_NAME

    try:
        # 默认质量下 jmcomic 已直接存 JPEG，这里无需再读再写
        if direct_jpeg and all(p.suffix.lower() in _JPEG_SUFFIXES for p in images):
            pages = [str(p) for p in images]
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            tmp_dir.mkdir(parents=True, exist_ok=True)
            pages = _convert_images(images, tmp_dir, quality, direct_jpeg, Image)

        if not pages:
            raise RuntimeError("没有可用于生成 PDF 的图片")

        _write_pdf(tmp_pdf, pages)
        _validate_pdf(tmp_pdf)
        os.replace(tmp_pdf, final_path)
        _remove_old_pdfs(album_root, final_path)
        return final_path
    finally:
        tmp_pdf.unlink(missing_ok=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _convert_images(
    images: list[Path],
    tmp_dir: Path,
    quality: int,
    direct_jpeg: bool,
    image_cls,
) -> list[str]:
    # 把非 JPEG（或需要重编码）的图片并行转成目标质量的 JPEG，按原顺序返回
    def convert_one(item: tuple[int, Path]) -> tuple[str | None, Path | None, Exception | None]:
        index, source = item
        target = tmp_dir / f"{index:05d}.jpg"
        try:
            with image_cls.open(source) as raw:
                rgb = raw if raw.mode in ("RGB", "L") else raw.convert("RGB")
                try:
                    rgb.save(target, format="JPEG", quality=quality)
                finally:
                    if rgb is not raw:
                        rgb.close()
        except (OSError, ValueError, SyntaxError) as e:
            return None, source, e
        return str(target), None, None

    work = [
        (index, source)
        for index, source in enumerate(images)
        if not (direct_jpeg and source.suffix.lower() in _JPEG_SUFFIXES)
    ]

    converted: dict[int, str] = {}
    if work:
        workers = min(_MAX_CONVERT_WORKERS, max(1, os.cpu_count() or 1), len(work))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(convert_one, work))

        failed = 0
        for (index, _source), (target, source, error) in zip(work, results):
            if target is not None:
                converted[index] = target
                continue
            failed += 1
            if failed == 1:
                logger.warning(
                    f"图片转换失败：{source.name}：{type(error).__name__}: {error}"
                )

        if failed:
            logger.warning(f"有 {failed} 张图片无法转换为 JPEG，已跳过")

    pages: list[str] = []
    for index, source in enumerate(images):
        if direct_jpeg and source.suffix.lower() in _JPEG_SUFFIXES:
            pages.append(str(source))
        elif index in converted:
            pages.append(converted[index])

    return pages


def _write_pdf(path: Path, pages: list[str]) -> None:
    from img2pdf import convert

    with path.open("wb") as handle:
        if "outputstream" in inspect.signature(convert).parameters:
            convert(*pages, outputstream=handle)
        else:
            # 老版本 img2pdf 不支持 outputstream，退回整段字节
            handle.write(convert(*pages))


def _validate_pdf(path: Path) -> None:
    # 拒绝空文件或后缀对不上的产物，避免把坏文件发出去
    if not path.is_file() or path.stat().st_size < 1024:
        raise RuntimeError("生成的 PDF 文件为空或过小")
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise RuntimeError("生成的 PDF 文件格式无效")


def _remove_old_pdfs(album_root: Path, keep: Path) -> None:
    # 成功替换后清掉旧命名的 PDF，避免 check_local 扫到过期文件
    for old_pdf in album_root.glob("*.pdf"):
        if old_pdf == keep:
            continue
        try:
            old_pdf.unlink(missing_ok=True)
        except OSError:
            continue
