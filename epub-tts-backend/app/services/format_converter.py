"""Format converter service — converts non-EPUB ebook formats to EPUB.

Uses Calibre's `ebook-convert` CLI (industry standard, best conversion quality).
"""
import asyncio
import shutil
from loguru import logger


def _find_ebook_convert() -> str | None:
    """Locate the ebook-convert binary."""
    return shutil.which("ebook-convert")


async def convert_mobi_to_epub(mobi_path: str, epub_path: str) -> None:
    """Convert a MOBI file to EPUB using Calibre's ebook-convert.

    Args:
        mobi_path: Path to the source .mobi file.
        epub_path: Path where the output .epub should be written.

    Raises:
        RuntimeError: If ebook-convert is not installed or conversion fails.
    """
    binary = _find_ebook_convert()
    if not binary:
        raise RuntimeError(
            "ebook-convert not found. Install Calibre: "
            "apt-get install calibre (Linux) or brew install calibre (macOS)"
        )

    logger.info(f"[FormatConverter] Converting {mobi_path} -> {epub_path}")

    proc = await asyncio.create_subprocess_exec(
        binary, mobi_path, epub_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()
        logger.error(f"[FormatConverter] ebook-convert failed: {err_msg}")
        raise RuntimeError(f"ebook-convert failed (exit {proc.returncode}): {err_msg}")

    logger.info("[FormatConverter] Conversion succeeded")
