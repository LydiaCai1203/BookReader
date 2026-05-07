"""Format converter service — converts non-EPUB ebook formats to EPUB.

Strategy: Use `mobi` Python package (pure Python, no external deps).
The `mobi` package uses KindleUnpack internally to extract MOBI content.
If the extracted result is a valid EPUB, use it directly.
Otherwise, extract HTML + metadata and build a proper EPUB.
"""
import os
import glob
import shutil
import uuid
import zipfile

from loguru import logger


def _is_valid_epub(path: str) -> bool:
    """Check if a file is a valid EPUB (ZIP with proper structure)."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            return "mimetype" in names or any(n.startswith("META-INF/") for n in names)
    except (zipfile.BadZipFile, Exception):
        return False


async def convert_mobi_to_epub(mobi_path: str, epub_path: str) -> None:
    """Convert a MOBI file to EPUB.

    Raises:
        RuntimeError: If conversion fails.
    """
    try:
        import mobi
    except ImportError:
        raise RuntimeError("mobi 包未安装，请运行 pip install mobi")

    logger.info(f"[FormatConverter] Extracting MOBI: {mobi_path}")
    tempdir, extracted_path = mobi.extract(mobi_path)

    try:
        # Check if extracted result is a valid EPUB
        if extracted_path and os.path.exists(extracted_path) and _is_valid_epub(extracted_path):
            shutil.copy2(extracted_path, epub_path)
            logger.info("[FormatConverter] Extracted valid EPUB from KF8 MOBI")
            return

        # Not a valid EPUB — build one from extracted HTML + OPF metadata
        logger.info("[FormatConverter] Extracted file is not valid EPUB, building from HTML")
        _build_epub_from_extracted(tempdir, epub_path)
        logger.info("[FormatConverter] EPUB built successfully")
    finally:
        if tempdir and os.path.isdir(tempdir):
            shutil.rmtree(tempdir, ignore_errors=True)


def _parse_opf_metadata(tempdir: str) -> dict:
    """Extract metadata (title, author, cover image path) from content.opf."""
    from bs4 import BeautifulSoup

    meta = {"title": "Unknown Title", "author": "Unknown Author", "cover_href": None}

    opf_files = glob.glob(os.path.join(tempdir, "**", "*.opf"), recursive=True)
    if not opf_files:
        return meta

    try:
        with open(opf_files[0], "r", encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        title_tag = soup.find("dc:title") or soup.find("title")
        if title_tag and title_tag.get_text().strip():
            meta["title"] = title_tag.get_text().strip()

        creator_tag = soup.find("dc:creator") or soup.find("creator")
        if creator_tag and creator_tag.get_text().strip():
            meta["author"] = creator_tag.get_text().strip()

        # Find cover image
        cover_meta = soup.find("meta", attrs={"name": "cover"})
        if cover_meta and cover_meta.get("content"):
            cover_id = cover_meta["content"]
            cover_item = soup.find("item", attrs={"id": cover_id})
            if cover_item and cover_item.get("href"):
                meta["cover_href"] = cover_item["href"]
    except Exception as e:
        logger.warning(f"[FormatConverter] Failed to parse OPF: {e}")

    return meta


# 每个章节大约多少段落
_PARAGRAPHS_PER_CHAPTER = 30


def _split_html_to_chapters(html_content: str) -> list[dict]:
    """Split a large HTML file into chapters.

    Strategy:
    - If the HTML has explicit heading tags (h1-h3), split by headings.
    - Otherwise, split evenly by paragraph count with numbered titles.

    Returns list of {"title": str, "html": str}.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_content, "html.parser")
    body = soup.find("body") or soup

    # Collect all block elements
    elements = body.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "div"])
    if not elements:
        return [{"title": "全文", "html": str(body)}]

    # Strategy 1: Try splitting by heading tags (h1-h3)
    heading_starts = []
    for i, el in enumerate(elements):
        if el.name in ("h1", "h2", "h3"):
            text = el.get_text().strip()
            if text:
                heading_starts.append((i, text[:80]))

    if len(heading_starts) >= 3:
        # Use headings as chapter boundaries
        chapters = []
        for idx, (start_pos, title) in enumerate(heading_starts):
            end_pos = heading_starts[idx + 1][0] if idx + 1 < len(heading_starts) else len(elements)
            chapter_els = elements[start_pos:end_pos]
            chapter_html = "\n".join(str(el) for el in chapter_els)
            if chapter_html.strip():
                chapters.append({"title": title, "html": chapter_html})
        if chapters:
            return chapters

    # Strategy 2: No headings — split evenly by paragraph count
    # Filter out empty elements
    non_empty = [(i, el) for i, el in enumerate(elements) if el.get_text().strip()]
    if not non_empty:
        return [{"title": "全文", "html": str(body)}]

    total = len(non_empty)
    if total <= _PARAGRAPHS_PER_CHAPTER:
        return [{"title": "全文", "html": str(body)}]

    chapters = []
    chapter_num = 1
    for start in range(0, total, _PARAGRAPHS_PER_CHAPTER):
        end = min(start + _PARAGRAPHS_PER_CHAPTER, total)
        chapter_els = [el for _, el in non_empty[start:end]]
        chapter_html = "\n".join(str(el) for el in chapter_els)
        if chapter_html.strip():
            chapters.append({
                "title": f"第 {chapter_num} 节",
                "html": chapter_html,
            })
            chapter_num += 1

    return chapters if chapters else [{"title": "全文", "html": str(body)}]


def _build_epub_from_extracted(tempdir: str, epub_path: str) -> None:
    """Build an EPUB from the extracted MOBI contents."""
    from ebooklib import epub
    from bs4 import BeautifulSoup

    # Parse metadata from OPF
    meta = _parse_opf_metadata(tempdir)

    # Find HTML files
    html_files = glob.glob(os.path.join(tempdir, "**", "*.html"), recursive=True)
    html_files += glob.glob(os.path.join(tempdir, "**", "*.htm"), recursive=True)

    if not html_files:
        raise RuntimeError("MOBI 中未找到 HTML 内容")

    html_files.sort()

    # Read all HTML content
    all_html = ""
    for hf in html_files:
        try:
            with open(hf, "r", encoding="utf-8", errors="replace") as f:
                all_html += f.read()
        except Exception:
            continue

    if not all_html.strip():
        raise RuntimeError("MOBI 中的 HTML 内容为空")

    # Split into chapters
    chapters = _split_html_to_chapters(all_html)

    # Build EPUB
    book = epub.EpubBook()
    book.set_identifier(f"mobi-{uuid.uuid4().hex[:12]}")
    book.set_title(meta["title"])
    book.set_language("zh")
    book.add_author(meta["author"])

    # Add cover image if found
    if meta["cover_href"]:
        opf_dir = os.path.dirname(
            glob.glob(os.path.join(tempdir, "**", "*.opf"), recursive=True)[0]
        )
        cover_path = os.path.join(opf_dir, meta["cover_href"])
        if os.path.exists(cover_path):
            try:
                with open(cover_path, "rb") as f:
                    cover_data = f.read()
                book.set_cover("cover.jpg", cover_data)
            except Exception as e:
                logger.warning(f"[FormatConverter] Failed to add cover: {e}")

    # Create chapter items
    epub_chapters = []
    spine = ["nav"]

    for i, ch in enumerate(chapters):
        # Clean the HTML
        soup = BeautifulSoup(ch["html"], "html.parser")
        clean_html = soup.decode_contents()
        if not clean_html.strip():
            continue

        epub_ch = epub.EpubHtml(
            title=ch["title"],
            file_name=f"chapter_{i}.xhtml",
            lang="zh",
        )
        epub_ch.content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{ch['title']}</title></head>
<body>
{clean_html}
</body>
</html>""".encode("utf-8")

        book.add_item(epub_ch)
        epub_chapters.append(epub_ch)
        spine.append(epub_ch)

    if not epub_chapters:
        raise RuntimeError("未能从 MOBI 中提取有效章节")

    # Add all images from extracted directory
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}
    for root, dirs, files in os.walk(tempdir):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in image_extensions:
                img_path = os.path.join(root, fname)
                try:
                    with open(img_path, "rb") as f:
                        img_content = f.read()
                    media_type = "image/jpeg"
                    if ext == ".png":
                        media_type = "image/png"
                    elif ext == ".gif":
                        media_type = "image/gif"
                    elif ext == ".svg":
                        media_type = "image/svg+xml"
                    elif ext == ".webp":
                        media_type = "image/webp"
                    img_item = epub.EpubImage()
                    img_item.file_name = f"Images/{fname}"
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
    logger.info(f"[FormatConverter] Built EPUB with {len(epub_chapters)} chapters")
