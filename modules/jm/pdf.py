# 图片合成 PDF
#
# 站点原图多为 webp，直接交给 img2pdf 会被无损转码、体积膨胀数倍；
# 因此逐张按指定质量转成 JPEG 再嵌入。逐张写临时文件而不是把全部
# 字节留在内存，避免大本子（数百页）占用过多内存。

from __future__ import annotations

import shutil
from pathlib import Path

from ...common.module_log import module_logger

logger = module_logger("jm")

_TMP_DIR_NAME = "__pdf_tmp__"


def make_pdf(album_root: Path, pdf_name: str, images: list[Path], quality: int) -> Path:
    # 生成 PDF 并返回路径；没有可用图片时抛 RuntimeError
    # 依赖在调用时才导入：缺库时让下载返回可读错误，而不是插件加载失败
    from img2pdf import convert
    from PIL import Image

    quality = max(1, min(95, int(quality)))
    tmp_dir = Path(album_root) / _TMP_DIR_NAME

    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        pages: list[str] = []
        failed = 0
        for index, source in enumerate(images):
            target = tmp_dir / f"{index:05d}.jpg"
            try:
                with Image.open(source) as raw:
                    raw.convert("RGB").save(
                        target, format="JPEG", quality=quality, optimize=True
                    )
            except (OSError, ValueError, SyntaxError) as e:
                # 单张坏图不该让整本失败；记下原因，最后汇总一次
                failed += 1
                if failed == 1:
                    logger.warning(
                        f"图片转换失败：{source.name}：{type(e).__name__}: {e}"
                    )
                continue
            pages.append(str(target))

        if failed:
            logger.warning(f"有 {failed} 张图片无法转换为 JPEG，已跳过")

        if not pages:
            raise RuntimeError("没有可用于生成 PDF 的图片")

        pdf_path = Path(album_root) / f"{pdf_name}.pdf"
        for old_pdf in Path(album_root).glob("*.pdf"):
            old_pdf.unlink(missing_ok=True)

        pdf_path.write_bytes(convert(pages))
        return pdf_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
