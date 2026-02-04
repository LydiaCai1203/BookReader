import os
import uuid
import shutil
import base64
import json
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from fastapi import UploadFile, HTTPException
from typing import List, Dict, Optional, Any
import hashlib
from datetime import datetime

UPLOAD_DIR = "data/uploads"
LIBRARY_INDEX_FILE = "data/uploads/library.json"


class BookLibrary:
    """书架管理 - 保存和管理已上传的书籍"""
    
    @staticmethod
    def _load_index() -> Dict:
        """加载书架索引"""
        if os.path.exists(LIBRARY_INDEX_FILE):
            try:
                with open(LIBRARY_INDEX_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {"books": {}}
        return {"books": {}}
    
    @staticmethod
    def _save_index(index: Dict) -> None:
        """保存书架索引"""
        os.makedirs(os.path.dirname(LIBRARY_INDEX_FILE), exist_ok=True)
        with open(LIBRARY_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def add_book(book_id: str, metadata: Dict, cover_url: Optional[str] = None) -> None:
        """添加书籍到书架"""
        index = BookLibrary._load_index()
        index["books"][book_id] = {
            "id": book_id,
            "title": metadata.get("title", "Unknown"),
            "creator": metadata.get("creator", "Unknown"),
            "language": metadata.get("language", ""),
            "publisher": metadata.get("publisher", ""),
            "coverUrl": cover_url,
            "addedAt": datetime.now().isoformat(),
            "lastOpenedAt": datetime.now().isoformat()
        }
        BookLibrary._save_index(index)
    
    @staticmethod
    def get_all_books() -> List[Dict]:
        """获取所有书籍列表"""
        index = BookLibrary._load_index()
        books = list(index["books"].values())
        # 按最后打开时间排序（最近的在前）
        books.sort(key=lambda x: x.get("lastOpenedAt", ""), reverse=True)
        return books
    
    @staticmethod
    def get_book(book_id: str) -> Optional[Dict]:
        """获取单本书的信息"""
        index = BookLibrary._load_index()
        return index["books"].get(book_id)
    
    @staticmethod
    def update_last_opened(book_id: str) -> None:
        """更新最后打开时间"""
        index = BookLibrary._load_index()
        if book_id in index["books"]:
            index["books"][book_id]["lastOpenedAt"] = datetime.now().isoformat()
            BookLibrary._save_index(index)
    
    @staticmethod
    def delete_book(book_id: str) -> bool:
        """从书架删除书籍"""
        index = BookLibrary._load_index()
        if book_id in index["books"]:
            del index["books"][book_id]
            BookLibrary._save_index(index)
            return True
        return False


class BookService:
    @staticmethod
    def get_book_path(book_id: str) -> str:
        return os.path.join(UPLOAD_DIR, f"{book_id}.epub")

    @staticmethod
    async def save_upload(file: UploadFile) -> str:
        # Generate ID based on content hash or random
        # For simplicity, random ID
        book_id = str(uuid.uuid4())
        file_path = BookService.get_book_path(book_id)
        
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return book_id

    @staticmethod
    def parse_metadata(book_id: str) -> Dict[str, Any]:
        path = BookService.get_book_path(book_id)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Book not found")
            
        try:
            book = epub.read_epub(path)
            
            # Helper to get metadata safely
            def get_meta(name: str, namespace: str = 'DC') -> str:
                try:
                    res = book.get_metadata(namespace, name)
                    if res:
                        return res[0][0]
                    return ""
                except:
                    return ""

            metadata = {
                "title": get_meta("title") or "Unknown Title",
                "creator": get_meta("creator") or "Unknown Author",
                "language": get_meta("language") or "en",
                "publisher": get_meta("publisher"),
                "pubdate": get_meta("date"),
            }
            
            # Extract Cover
            cover_url = None
            # Ebooklib way to find cover
            # Often it is an item with id 'cover' or check metadata
            # For simplicity, we skip complex cover extraction for now or return a placeholder
            # If we want cover, we need to extract image item and save it to static folder
            
            # Try to find cover image
            cover_item = None
            for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                if 'cover' in item.get_name().lower() or 'cover' in item.get_id().lower():
                    cover_item = item
                    break
            
            if cover_item:
                cover_filename = f"{book_id}_cover.jpg" # Assume jpg/png
                cover_path = os.path.join(UPLOAD_DIR, cover_filename)
                with open(cover_path, "wb") as f:
                    f.write(cover_item.get_content())
                cover_url = f"/covers/{cover_filename}"

            return {"metadata": metadata, "coverUrl": cover_url}
        except Exception as e:
            print(f"Error parsing metadata: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse EPUB")

    @staticmethod
    def get_toc(book_id: str) -> List[Dict[str, Any]]:
        path = BookService.get_book_path(book_id)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Book not found")
            
        book = epub.read_epub(path)
        toc = []
        
        # Recursive function to parse TOC
        def parse_nav_map(nav_point):
            # Ebooklib TOC structure can be complex (tuple or Link object)
            # Typically: (Link, [child_links]) or Link
            if isinstance(nav_point, tuple) or isinstance(nav_point, list):
                link = nav_point[0]
                children = nav_point[1] if len(nav_point) > 1 else []
            else:
                link = nav_point
                children = []
                
            if hasattr(link, 'href') and hasattr(link, 'title'):
                item = {
                    "id": str(uuid.uuid4()), # Generate transient ID
                    "href": link.href,
                    "label": link.title,
                    "subitems": [parse_nav_map(c) for c in children]
                }
                return item
            return None

        # Process book.toc
        for item in book.toc:
            parsed = parse_nav_map(item)
            if parsed:
                toc.append(parsed)
                
        # If TOC is empty, fallback to spine
        if not toc:
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                     toc.append({
                         "id": item.get_id(),
                         "href": item.get_name(),
                         "label": item.get_name(), # Fallback label
                         "subitems": []
                     })
                     
        return toc

    @staticmethod
    def get_chapter_content(book_id: str, href: str) -> Dict[str, Any]:
        path = BookService.get_book_path(book_id)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Book not found")
            
        book = epub.read_epub(path)
        
        # Href might contain anchor like chapter1.html#section1
        # ebooklib items are keyed by filename usually
        anchor = None
        if '#' in href:
            base_href, anchor = href.split('#', 1)
        else:
            base_href = href
        
        # Find item by href
        target_item = None
        for item in book.get_items():
            item_name = item.get_name()
            # 尝试多种匹配方式
            if item_name == base_href or item_name.endswith('/' + base_href) or base_href.endswith(item_name):
                target_item = item
                break
                
        if not target_item:
            # Try searching by ID if href failed?
            # Or try relative paths logic
            raise HTTPException(status_code=404, detail=f"Chapter {href} not found")
            
        # Parse HTML content
        content = target_item.get_content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # 如果有锚点，尝试定位到特定元素
        target_element = None
        if anchor:
            # 尝试通过 id 查找
            target_element = soup.find(id=anchor)
            # 如果没找到，尝试通过 name 属性查找
            if not target_element:
                target_element = soup.find(attrs={"name": anchor})
        
        # 提取文本（保留结构）
        heading_tags = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
        block_tags = {'p', 'div', 'section', 'article', 'blockquote'}
        list_tags = {'ul', 'ol', 'nav', 'dl'}
        list_item_tags = {'li', 'dt', 'dd'}
        
        def extract_structured_text(element):
            """递归提取文本，保留结构"""
            if element is None:
                return ""
            
            # 处理字符串节点
            if isinstance(element, str) or hasattr(element, 'strip') and not hasattr(element, 'name'):
                text = str(element).strip()
                return text if text else ""
            
            # 没有 name 属性的节点
            if not hasattr(element, 'name') or element.name is None:
                if hasattr(element, 'get_text'):
                    return element.get_text().strip()
                return str(element).strip()
            
            tag_name = element.name
            
            # 标题标签：前后加双换行
            if tag_name in heading_tags:
                text = element.get_text(separator=' ').strip()
                return f"\n\n{text}\n\n" if text else ""
            
            # 列表容器：递归处理子元素
            if tag_name in list_tags:
                parts = []
                for child in element.children:
                    child_text = extract_structured_text(child)
                    if child_text:
                        parts.append(child_text)
                return '\n'.join(parts)
            
            # 列表项：每项单独一行
            if tag_name in list_item_tags:
                text = element.get_text(separator=' ').strip()
                return f"{text}\n" if text else ""
            
            # 块级元素：内容后加换行
            if tag_name in block_tags:
                text = element.get_text(separator=' ').strip()
                return f"{text}\n" if text else ""
            
            # 其他元素：递归处理子元素
            if hasattr(element, 'children'):
                parts = []
                for child in element.children:
                    child_text = extract_structured_text(child)
                    if child_text:
                        parts.append(child_text)
                return ' '.join(parts) if parts else ""
            
            # 兜底：直接获取文本
            if hasattr(element, 'get_text'):
                return element.get_text(separator=' ').strip()
            return ""
        
        if target_element:
            # 找到锚点元素后，提取该元素及其后续兄弟元素的内容
            parts = [extract_structured_text(target_element)]
            
            # 获取后续兄弟元素，直到遇到下一个标题标签
            for sibling in target_element.find_next_siblings():
                if hasattr(sibling, 'name') and sibling.name in heading_tags and sibling.get('id'):
                    break
                sibling_text = extract_structured_text(sibling)
                if sibling_text:
                    parts.append(sibling_text)
            
            text = '\n'.join(parts)
        else:
            # 没有锚点或找不到锚点元素，遍历 body 的直接子元素
            body = soup.find('body') or soup
            parts = []
            for child in body.children:
                child_text = extract_structured_text(child)
                if child_text:
                    parts.append(child_text)
            text = '\n'.join(parts)
        
        # 智能分段/分句处理
        import re
        
        # 清理多余的空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 按行分割
        all_lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not all_lines:
            return {
                "href": href,
                "text": text,
                "sentences": [text.strip()] if text.strip() else []
            }
        
        # 判断整个页面是否是"目录型"内容
        # 特征：大多数行较短、很少以句号结尾
        short_lines = sum(1 for line in all_lines if len(line) < 60)
        sentence_endings = sum(1 for line in all_lines if line.endswith(('。', '！', '？', '.', '!', '?')))
        
        is_toc_like = (
            len(all_lines) >= 3 and
            short_lines / len(all_lines) > 0.7 and  # 70%以上是短行
            sentence_endings / len(all_lines) < 0.3  # 少于30%以句号结尾
        )
        
        if is_toc_like:
            # 目录型：每行独立显示
            sentences = all_lines
        else:
            # 普通内容：按段落处理
            paragraphs = re.split(r'\n\s*\n', text)
            sentences = []
            
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                
                lines = [line.strip() for line in para.split('\n') if line.strip()]
                
                if len(lines) == 1:
                    # 单行段落：可能是标题，保持独立
                    if len(lines[0]) < 60:
                        sentences.append(lines[0])
                    else:
                        # 长行：按句子分割
                        split_sentences = re.split(r'(?<=[.!?。！？；])\s*', lines[0])
                        for s in split_sentences:
                            s = s.strip()
                            if s and len(s) > 1:
                                sentences.append(s)
                else:
                    # 多行段落：合并后按句子分割
                    combined = ' '.join(lines)
                    split_sentences = re.split(r'(?<=[.!?。！？；])\s*', combined)
                    for s in split_sentences:
                        s = s.strip()
                        if s and len(s) > 1:
                            sentences.append(s)
        
        # 如果分句后为空，至少返回整个文本作为一句
        if not sentences and text.strip():
            sentences = [text.strip()]
        
        return {
            "href": href,
            "text": text,
            "sentences": sentences
        }
