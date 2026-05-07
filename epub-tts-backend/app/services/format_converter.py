"""Format converter service — converts non-EPUB ebook formats to EPUB.

Strategy:
1. Try `mobi` Python package (pure Python, no external deps) — unpacks MOBI to EPUB/HTML
2. Fallback to Calibre `ebook-convert` CLI if available

The `mobi` package (pip install mobi) uses KindleUnpack internally.
For KF8 (newer Kindle format), it directly extracts the embedded EPUB.
For older MOBI, it extracts HTML which we then wrap into an EPUB.
"""
import os
import glob
import shutil
import tempfile
import uuid

from loguru import logger


async def convert_mobi_to_epub(mobi_path: str, epub_path: str) -> None:
    """Convert a MOBI file to EPUB.

    Args:
        mobi_path: Path to the source .mobi file.
        epub_path: Path where the output .epub should be written.

    Raises:
        RuntimeError: If conversion fails.
    """
    # Strategy 1: Use `mobi` package (pure Python)
    try:
        import mobi
        logger.info(f"[FormatConverter] Using mobi package: {mobi_path} -> {epub_path}")

        tempdir, extracted_epub = mobi.extract(mobi_path)

        try:
            if extracted_epub and os.path.exists(extracted_epub):
                # KF8 format — mobi package directly extracted an EPUB
                shutil.copy2(extracted_epub, epub_path)
                logger.info("[FormatConverter] Extracted EPUB from KF8 MOBI")
                return

            # Older MOBI format — find extracted HTML and build EPUB
            html_files = glob.glob(os.path.join(tempdir, "**", "*.html"), recursive=True)
            html_files += glob.glob(os.path.join(tempdir, "**", "*.htm"), recursive=True)

            if not html_files:
                raise RuntimeError("No HTML content found in extracted MOBI")

            _build_epub_from_html(html_files, epub_path, tempdir)
            logger.info("[FormatConverter] Built EPUB from MOBI HTML content")
        finally:
            # Clean up the temp directory created by mobi.extract
            if tempdir and os.path.isdir(tempdir):
                shutil.rmtree(tempdir, ignore_errors=True)
        return

    except ImportError:
        logger.warning("[FormatConverter] mobi package not installed, trying Calibre")
    except Exception as e:
        logger.warning(f"[FormatConverter] mobi package failed: {e}, trying Calibre")

    # Strategy 2: Fallback to Calibre CLI
    import asyncio
    binary = shutil.which("ebook-convert")
    if not binary:
        raise RuntimeError(
            "MOBI 转换失败：请安装 mobi 包 (pip install mobi) 或 Calibre (apt-get install calibre)"
        )

    logger.info(f"[FormatConverter] Using Calibre: {mobi_path} -> {epub_path}")
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

    logger.info("[FormatConverter] Calibre conversion succeeded")


def _build_epub_from_html(
    html_files: list[str], epub_path: str, tempdir: str
) -> None:
    """Build an EPUB from extracted HTML files."""
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.EpubBook()
    book.set_identifier(f"mobi-{uuid.uuid4().hex[:12]}")
    book.set_language("en")

    # Try to extract title from the first HTML
    title = "Unknown Title"
    author = "Unknown Author"

    # Sort HTML files for consistent ordering
    html_files.sort()

    epub_chapters = []
    spine = ["nav"]

    for i, html_file in enumerate(html_files):
        try:
            with open(html_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue

        soup = BeautifulSoup(content, "html.parser")

        # Extract title from first file
        if i == 0:
            title_tag = soup.find("title")
            if title_tag and title_tag.get_text().strip():
                title = title_tag.get_text().strip()
            # Try to find author in meta
            author_meta = soup.find("meta", attrs={"name": "author"})
            if author_meta and author_meta.get("content"):
                author = author_meta["content"]

        # Extract body content
        body = soup.find("body")
        body_html = str(body) if body else content

        # Find chapter title from heading
        chapter_title = f"Chapter {i + 1}"
        heading = soup.find(["h1", "h2", "h3"])
        if heading and heading.get_text().strip():
            chapter_title = heading.get_text().strip()[:100]

        chapter_id = f"chapter_{i}"
        epub_ch = epub.EpubHtml(
            title=chapter_title,
            file_name=f"{chapter_id}.xhtml",
            lang="en",
        )
        epub_ch.content = body_html
        book.add_item(epub_ch)
        epub_chapters.append(epub_ch)
        spine.append(epub_ch)

    if not epub_chapters:
        raise RuntimeError("No valid HTML content extracted from MOBI")

    book.set_title(title)
    book.add_author(author)

    # Add images found in tempdir
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}
    for root, dirs, files in os.walk(tempdir):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in image_extensions:
                img_path = os.path.join(root, fname)
                rel_path = os.path.relpath(img_path, tempdir)
                try:
                    with open(img_path, "rb") as f:
                        img_content = f.read()
                    media_type = f"image/{ext.lstrip('.')}"
                    if ext == ".svg":
                        media_type = "image/svg+xml"
                    elif ext in (".jpg", ".jpeg"):
                        media_type = "image/jpeg"
                    img_item = epub.EpubImage()
                    img_item.file_name = f"images/{fname}"
                    img_item.media_type = media_type
                    img_item.content = img_content
                    book.add_item(img_item)
                except Exception:
                    pass

    # TOC and navigation
    book.toc = [
        epub.Link(ch.file_name, ch.title, ch.file_name.replace(".xhtml", ""))
        for ch in epub_chapters
    ]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub.write_epub(epub_path, book)
