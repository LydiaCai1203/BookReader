"""GitBook import service — scrapes GitBook sites and builds EPUB files.

Handles both modern (Next.js SPA) and legacy (static HTML) GitBook sites.
Limits to 500 pages max to prevent abuse.
"""
import asyncio

import json
import os
import re
import uuid
from typing import Callable, Optional
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


async def import_gitbook(url: str, user_id: str, on_progress: Optional[Callable] = None) -> dict:
    """Import a GitBook site as an EPUB book.

    This is the main entry point called from the background task.
    on_progress(current, total, title) is called after each page fetch.
    Returns dict with book info on success.
    """
    book_id = str(uuid.uuid4())
    book_dir = settings.get_user_book_dir(user_id, book_id)
    os.makedirs(book_dir, exist_ok=True)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=10.0),
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
                toc_links = [{"title": site_title, "url": url}]

            def _flatten_toc(items: list[dict]) -> list[dict]:
                flat = []
                for item in items:
                    flat.append(item)
                    flat.extend(_flatten_toc(item.get("subitems", [])))
                return flat

            flat_links = _flatten_toc(toc_links)

            if len(flat_links) > MAX_PAGES:
                logger.warning(
                    f"[GitBook] TOC has {len(flat_links)} pages, truncating to {MAX_PAGES}"
                )
                flat_links = flat_links[:MAX_PAGES]

            # Fetch all pages
            chapters = []

            total_pages = len(flat_links)
            CONCURRENCY = 5
            semaphore = asyncio.Semaphore(CONCURRENCY)

            async def fetch_page(i: int, link: dict) -> dict | None:
                async with semaphore:
                    page_url = link["url"]
                    page_title = link["title"]
                    logger.info(
                        f"[GitBook] Fetching page {i + 1}/{total_pages}: {page_title}"
                    )
                    try:
                        page_resp = await client.get(page_url)
                        page_resp.raise_for_status()
                        page_html = page_resp.text
                        content = _extract_page_content(page_html)
                        if content.strip():
                            return {
                                "index": i,
                                "title": page_title,
                                "content": content,
                                "source_url": page_url,
                            }
                    except Exception as e:
                        logger.warning(f"[GitBook] Failed to fetch {page_url}: {e}")
                    return None

            tasks = [fetch_page(i, link) for i, link in enumerate(flat_links)]
            results = await asyncio.gather(*tasks)

            # Sort by original order and filter None
            fetched = sorted(
                [r for r in results if r is not None],
                key=lambda x: x["index"],
            )

            if on_progress:
                on_progress(current=total_pages, total=total_pages, title=site_title)

            # Keep original image URLs (no download needed for online reading)
            for page in fetched:
                chapters.append({
                    "title": page["title"],
                    "content": page["content"],
                    "source_url": page["source_url"],
                })

            if not chapters:
                raise GitBookImportError("No content could be extracted from the GitBook")

            # Build EPUB
            epub_path = settings.get_book_path(user_id, book_id)
            _build_epub(
                title=site_title,
                chapters=chapters,
                output_path=epub_path,
                source_url=url,
                toc_tree=toc_links,
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
                toc_json=json.dumps(toc, ensure_ascii=False),
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


def _detect_site_type(soup: BeautifulSoup) -> str:
    """Use AI to detect documentation site type."""
    # Extract relevant HTML snippets for analysis
    nav_snippet = ""
    for selector in ["nav", "aside", "[role='navigation']", ".sidebar", ".toc"]:
        el = soup.select_one(selector)
        if el:
            nav_snippet = str(el)[:2000]  # First 2000 chars
            break

    if not nav_snippet:
        return "unknown"

    # Check for obvious patterns first (fast path)
    if soup.find("div", class_=re.compile(r"md-sidebar--primary")):
        return "mkdocs"
    if soup.find("script", id="__NEXT_DATA__"):
        return "gitbook"
    if soup.find(class_=re.compile(r"docusaurus", re.I)):
        return "docusaurus"

    # TODO: AI call for unknown types
    # For now, return generic
    return "generic"


def _extract_toc_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract table of contents links from the GitBook sidebar/navigation."""
    links = []
    seen_urls = set()
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc

    # Strategy 1: MkDocs / ReadTheDocs — nested nav with sections
    mkdocs_sidebar = soup.find("div", class_=re.compile(r"md-sidebar--primary", re.I))
    if mkdocs_sidebar:
        nav_el = mkdocs_sidebar.find("nav")
        if nav_el:
            links = _extract_mkdocs_toc(nav_el, base_url, base_domain)
            if links:
                return links

    # Strategy 2: Look for nav/sidebar elements common in GitBook
    nav_selectors = [
        soup.find("nav", class_=re.compile(r"sidebar|toc|table-of-contents", re.I)),
        soup.find(attrs={"role": "navigation"}),
        soup.find(class_=re.compile(r"sidebar|side-bar|table-of-contents", re.I)),
        soup.find("nav"),
        soup.find(attrs={"data-testid": re.compile(r"sidebar|navigation|toc", re.I)}),
    ]

    for nav_el in nav_selectors:
        if nav_el is None:
            continue
        for a in nav_el.find_all("a", href=True):
            href = a["href"]
            # Skip anchor-only links
            if href.startswith("#"):
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Only same-domain links, skip external
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

    # Strategy 3: Look for __NEXT_DATA__ (modern GitBook)
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


def _extract_mkdocs_toc(nav_el, base_url: str, base_domain: str) -> list[dict]:
    """Extract TOC from MkDocs nested nav structure, returning nested subitems."""
    seen_urls = set()

    def _walk_items(parent_el) -> list[dict]:
        ul = parent_el.find("ul", recursive=False)
        if not ul:
            inner_nav = parent_el.find("nav", recursive=False)
            if inner_nav:
                ul = inner_nav.find("ul", recursive=False)
        if not ul:
            return []

        items = []
        for li in ul.find_all("li", recursive=False):
            a_tag = li.find("a", recursive=False)
            label_tag = li.find("label", recursive=False)
            item = None

            if a_tag:
                href = a_tag.get("href", "")
                title = a_tag.get_text().strip()
                if title and not href.startswith("#"):
                    full_url = urljoin(base_url, href)
                    parsed = urlparse(full_url)
                    if parsed.netloc == base_domain:
                        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                        if clean_url not in seen_urls:
                            seen_urls.add(clean_url)
                            item = {"title": title, "url": clean_url, "subitems": []}

            # Recurse into sub-navigation (skip secondary/TOC navs)
            sub_nav = li.find("nav", recursive=False)
            if sub_nav and "secondary" not in " ".join(sub_nav.get("class", [])):
                children = _walk_items(sub_nav)
            elif not sub_nav and li.find("ul", recursive=False):
                children = _walk_items(li)
            else:
                children = []

            if item:
                item["subitems"] = children
                items.append(item)
            elif children:
                # Section label with no direct link — create virtual parent node
                section_title = label_tag.get_text().strip() if label_tag else ""
                if section_title:
                    items.append({"title": section_title, "url": children[0]["url"], "subitems": children})
                else:
                    items.extend(children)

        return items

    return _walk_items(nav_el)


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

    # Try to find the main content area — prefer the most specific element
    content_selectors = [
        soup.find("article"),
        soup.find(class_=re.compile(r"markdown-body|md-typeset|page-body|page-content|main-content", re.I)),
        soup.find("main"),
        soup.find(attrs={"role": "main"}),
        soup.find(class_=re.compile(r"content", re.I)),
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

    # Remove MkDocs / ReadTheDocs / GitBook decorative elements
    # 1. GitHub edit buttons, source links
    for el in content_el.find_all(
        "a", class_=re.compile(r"md-content__button|md-icon|edit-page|headerlink", re.I)
    ):
        el.decompose()
    # 2. Standalone SVG elements (icons)
    for svg in content_el.find_all("svg"):
        svg.decompose()
    # 3. "Permanent link" ¶ anchors (headerlink class)
    for el in content_el.find_all("a", class_="headerlink"):
        el.decompose()
    # 4. GitBook hint/callout close buttons, action buttons
    for el in content_el.find_all(
        class_=re.compile(r"gitbook-drawing|copy-button|clipboard", re.I)
    ):
        el.decompose()

    # Return the inner HTML (children), stripping the outer wrapper tag itself
    return content_el.decode_contents()


def _build_epub(
    title: str,
    chapters: list[dict],
    output_path: str,
    source_url: str,
    toc_tree: list[dict] | None = None,
) -> None:
    """Build an EPUB file from extracted GitBook chapters."""
    book = epub.EpubBook()

    book.set_identifier(f"gitbook-{uuid.uuid4().hex[:12]}")
    book.set_title(title)
    book.set_language("en")
    book.add_author("GitBook")
    book.add_metadata("DC", "source", source_url)

    parsed_base = urlparse(source_url)
    base_domain = parsed_base.netloc

    # Build URL → filename mapping for internal link rewriting
    url_to_filename: dict[str, str] = {}
    for i, ch in enumerate(chapters):
        filename = f"chapter_{i}.xhtml"
        src_url = ch.get("source_url", "")
        if src_url:
            # Map full URL
            url_to_filename[src_url] = filename
            # Map path only (for relative links)
            parsed = urlparse(src_url)
            url_to_filename[parsed.path] = filename
            # Map path without trailing slash
            stripped = parsed.path.rstrip("/")
            if stripped:
                url_to_filename[stripped] = filename
                url_to_filename[stripped + "/"] = filename

    # Create chapters
    epub_chapters = []
    src_url_to_epub_ch = {}
    spine = ["nav"]

    for i, ch in enumerate(chapters):
        filename = f"chapter_{i}.xhtml"

        # Parse and clean content, rewrite internal links
        content_soup = BeautifulSoup(ch["content"], "html.parser")

        # Rewrite <a href="..."> links that point to other chapters
        for a_tag in content_soup.find_all("a", href=True):
            href = a_tag["href"]
            resolved = urljoin(ch.get("source_url", source_url), href)
            parsed = urlparse(resolved)

            # Only rewrite same-domain links
            if parsed.netloc and parsed.netloc != base_domain:
                continue

            # Try to find a matching chapter filename
            target = (
                url_to_filename.get(resolved)
                or url_to_filename.get(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
                or url_to_filename.get(parsed.path)
                or url_to_filename.get(parsed.path.rstrip("/"))
            )
            if target:
                fragment = f"#{parsed.fragment}" if parsed.fragment else ""
                a_tag["href"] = f"{target}{fragment}"
            else:
                # External or unmatched link — keep as absolute URL so it doesn't break
                if not href.startswith("http"):
                    a_tag["href"] = resolved

        plain_text = content_soup.get_text(separator="\n").strip()
        if not plain_text:
            continue

        epub_ch = epub.EpubHtml(
            title=ch["title"],
            file_name=filename,
            lang="en",
        )

        clean_content = content_soup.decode_contents()

        # Only add <h1> if content doesn't already have one
        has_h1 = content_soup.find("h1") is not None
        title_heading = "" if has_h1 else f"<h1>{ch['title']}</h1>\n"

        epub_ch.content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{ch['title']}</title></head>
<body>
{title_heading}{clean_content}
</body>
</html>""".encode("utf-8")

        try:
            body = epub_ch.get_body_content()
            if not body or not body.strip():
                raise ValueError("empty body")
        except Exception:
            escaped_text = plain_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            paragraphs = "\n".join(f"<p>{line}</p>" for line in escaped_text.splitlines() if line.strip())
            epub_ch.content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{ch['title']}</title></head>
<body>
<h1>{ch['title']}</h1>
{paragraphs}
</body>
</html>""".encode("utf-8")
            logger.warning(f"[GitBook] Chapter '{ch['title']}' fell back to plain text")

        book.add_item(epub_ch)
        epub_chapters.append(epub_ch)
        src_url_to_epub_ch[ch.get("source_url", "")] = epub_ch
        spine.append(epub_ch)

    if not epub_chapters:
        raise GitBookImportError("No valid content could be extracted from the GitBook")

    # Table of contents — use nested toc_tree if available
    def _build_toc_entry(node: dict):
        ch = src_url_to_epub_ch.get(node["url"])
        children = [e for sub in node.get("subitems", []) for e in [_build_toc_entry(sub)] if e]
        if ch:
            link = epub.Link(ch.file_name, node["title"], ch.file_name.replace(".xhtml", ""))
            return (link, children) if children else link
        # No page for this node — promote children directly
        return children if children else None

    if toc_tree:
        toc_entries = []
        for node in toc_tree:
            entry = _build_toc_entry(node)
            if entry is None:
                continue
            if isinstance(entry, list):
                toc_entries.extend(entry)
            else:
                toc_entries.append(entry)
        book.toc = toc_entries
    else:
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
    logger.info(f"[GitBook] EPUB written to {output_path} ({len(epub_chapters)} chapters)")



