"""GitBook import service — scrapes GitBook sites and builds EPUB files.

Handles both modern (Next.js SPA) and legacy (static HTML) GitBook sites.
Limits to 500 pages max to prevent abuse.
"""
import os
import re
import uuid
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from ebooklib import epub
from loguru import logger

from shared.config import settings
from shared.database import get_db
from shared.models import Book

MAX_PAGES = 500
REQUEST_TIMEOUT = 30.0


class GitBookImportError(Exception):
    pass


async def import_gitbook(url: str, user_id: str) -> dict:
    """Import a GitBook site as an EPUB book.

    This is the main entry point called from the background task.
    Returns dict with book info on success.
    """
    book_id = str(uuid.uuid4())
    book_dir = settings.get_user_book_dir(user_id, book_id)
    os.makedirs(book_dir, exist_ok=True)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BookReader/1.0)"},
        ) as client:
            # Fetch the main page to extract TOC and title
            logger.info(f"[GitBook] Fetching main page: {url}")
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

            soup = BeautifulSoup(html, "html.parser")
            site_title = _extract_site_title(soup, url)

            # Try to extract TOC links from sidebar / navigation
            toc_links = _extract_toc_links(soup, url)
            if not toc_links:
                # Single-page GitBook or unrecognized structure
                toc_links = [{"title": site_title, "url": url}]

            if len(toc_links) > MAX_PAGES:
                logger.warning(
                    f"[GitBook] TOC has {len(toc_links)} pages, truncating to {MAX_PAGES}"
                )
                toc_links = toc_links[:MAX_PAGES]

            # Fetch all pages
            chapters = []
            for i, link in enumerate(toc_links):
                page_url = link["url"]
                page_title = link["title"]
                logger.info(
                    f"[GitBook] Fetching page {i + 1}/{len(toc_links)}: {page_title}"
                )
                try:
                    page_resp = await client.get(page_url)
                    page_resp.raise_for_status()
                    page_html = page_resp.text
                    content = _extract_page_content(page_html)
                    if content.strip():
                        chapters.append({
                            "title": page_title,
                            "content": content,
                        })
                except Exception as e:
                    logger.warning(f"[GitBook] Failed to fetch {page_url}: {e}")
                    continue

            if not chapters:
                raise GitBookImportError("No content could be extracted from the GitBook")

            # Build EPUB
            epub_path = settings.get_book_path(user_id, book_id)
            _build_epub(
                title=site_title,
                chapters=chapters,
                output_path=epub_path,
                source_url=url,
            )

        # Parse metadata and cover from the generated EPUB
        from app.services.book_service import BookService

        meta_info = BookService.parse_metadata(book_id, user_id)
        # Override title with the GitBook site title (EPUB metadata may be generic)
        meta_info["metadata"]["title"] = site_title

        toc = BookService.get_toc(book_id, user_id)
        cover_url = meta_info["coverUrl"]

        # Save to database
        with get_db() as db:
            book = Book(
                id=book_id,
                user_id=user_id,
                title=site_title,
                creator="GitBook",
                cover_url=cover_url,
                file_path=epub_path,
                is_public=False,
                source_type="gitbook",
                source_url=url,
            )
            db.add(book)
            db.commit()

        return {
            "bookId": book_id,
            "title": site_title,
            "status": "completed",
            "totalPages": len(chapters),
        }

    except GitBookImportError:
        # Clean up on known errors
        import shutil
        if os.path.isdir(book_dir):
            shutil.rmtree(book_dir)
        raise
    except Exception as e:
        import shutil
        if os.path.isdir(book_dir):
            shutil.rmtree(book_dir)
        logger.exception(f"[GitBook] Import failed: {e}")
        raise GitBookImportError(f"Import failed: {str(e)}")


def _extract_site_title(soup: BeautifulSoup, url: str) -> str:
    """Extract the site title from the page."""
    # Try <title> tag
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip()
        # Remove common suffixes like " | GitBook" or " - GitBook"
        title = re.sub(r"\s*[|\-–—]\s*GitBook\s*$", "", title, flags=re.IGNORECASE)
        if title:
            return title

    # Try og:title
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    # Fallback to domain
    parsed = urlparse(url)
    return parsed.netloc


def _extract_toc_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract table of contents links from the GitBook sidebar/navigation."""
    links = []
    seen_urls = set()
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc

    # Strategy 1: Look for nav/sidebar elements common in GitBook
    nav_selectors = [
        soup.find("nav"),
        soup.find(attrs={"role": "navigation"}),
        soup.find(class_=re.compile(r"sidebar|side-bar|navigation|nav|toc|table-of-contents", re.I)),
        soup.find(attrs={"data-testid": re.compile(r"sidebar|navigation|toc", re.I)}),
    ]

    for nav_el in nav_selectors:
        if nav_el is None:
            continue
        for a in nav_el.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Only same-domain links, skip anchors and external
            if parsed.netloc != base_domain:
                continue
            # Normalize: remove fragment
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if clean_url in seen_urls:
                continue

            title = a.get_text().strip()
            if not title:
                continue

            seen_urls.add(clean_url)
            links.append({"title": title, "url": clean_url})

        if links:
            break  # Use first nav element that yields results

    # Strategy 2: Look for __NEXT_DATA__ (modern GitBook)
    if not links:
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if script_tag:
            import json
            try:
                next_data = json.loads(script_tag.string or "{}")
                # Navigate the Next.js data structure to find pages
                pages = _extract_pages_from_next_data(next_data, base_url)
                if pages:
                    links = pages
            except (json.JSONDecodeError, KeyError):
                pass

    return links


def _extract_pages_from_next_data(data: dict, base_url: str) -> list[dict]:
    """Try to extract page list from Next.js __NEXT_DATA__ JSON."""
    pages = []
    try:
        # Modern GitBook stores pages in props.pageProps
        props = data.get("props", {}).get("pageProps", {})

        # Try common structures
        space = props.get("space", {})
        space_pages = space.get("pages", [])

        if space_pages:
            for page in space_pages:
                title = page.get("title", "")
                path = page.get("path", "")
                if title and path:
                    full_url = urljoin(base_url, path)
                    pages.append({"title": title, "url": full_url})
    except Exception:
        pass

    return pages


def _extract_page_content(html: str) -> str:
    """Extract the main content from a GitBook page as clean HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, nav, header, footer elements
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()

    # Try to find the main content area
    content_selectors = [
        soup.find("main"),
        soup.find(attrs={"role": "main"}),
        soup.find(class_=re.compile(r"page-body|page-content|content|markdown-body|main-content", re.I)),
        soup.find("article"),
    ]

    content_el = None
    for el in content_selectors:
        if el is not None:
            content_el = el
            break

    if content_el is None:
        # Fallback: use body
        content_el = soup.find("body")

    if content_el is None:
        return ""

    # Remove sidebar/navigation elements within content
    for sidebar in content_el.find_all(
        class_=re.compile(r"sidebar|side-bar|navigation|nav-", re.I)
    ):
        sidebar.decompose()

    return str(content_el)


def _build_epub(
    title: str,
    chapters: list[dict],
    output_path: str,
    source_url: str,
) -> None:
    """Build an EPUB file from extracted GitBook chapters."""
    book = epub.EpubBook()

    book.set_identifier(f"gitbook-{uuid.uuid4().hex[:12]}")
    book.set_title(title)
    book.set_language("en")
    book.add_author("GitBook")
    book.add_metadata("DC", "source", source_url)

    # Create chapters
    epub_chapters = []
    spine = ["nav"]

    for i, ch in enumerate(chapters):
        chapter_id = f"chapter_{i}"
        filename = f"{chapter_id}.xhtml"

        epub_ch = epub.EpubHtml(
            title=ch["title"],
            file_name=filename,
            lang="en",
        )
        epub_ch.content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{ch['title']}</title></head>
<body>
<h1>{ch['title']}</h1>
{ch['content']}
</body>
</html>"""

        book.add_item(epub_ch)
        epub_chapters.append(epub_ch)
        spine.append(epub_ch)

    # Table of contents
    book.toc = [
        epub.Link(ch.file_name, ch.title, ch.file_name.replace(".xhtml", ""))
        for ch in epub_chapters
    ]

    # Navigation
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Spine
    book.spine = spine

    epub.write_epub(output_path, book)
    logger.info(f"[GitBook] EPUB written to {output_path} ({len(chapters)} chapters)")
