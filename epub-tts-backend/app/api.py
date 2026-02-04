from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
from app.services.book_service import BookService, BookLibrary
from app.services.tts_service import TTSService, AudioCache, AUDIO_DIR
from app.services.task_service import task_manager, TaskStatus
import asyncio
import os
import edge_tts

router = APIRouter()

# --- Data Models ---
class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "en-US-ChristopherNeural" # Default voice
    rate: Optional[float] = 1.0
    pitch: Optional[float] = 1.0
    volume: Optional[float] = 1.0

class DownloadRequest(BaseModel):
    """下载音频请求"""
    sentences: List[str]  # 要合成的句子列表
    voice: Optional[str] = "zh-CN-XiaoxiaoNeural"
    rate: Optional[float] = 1.0
    pitch: Optional[float] = 1.0
    filename: Optional[str] = "chapter"  # 下载文件名（不含扩展名）

class BookDownloadRequest(BaseModel):
    """下载整本书音频请求"""
    voice: Optional[str] = "zh-CN-XiaoxiaoNeural"
    rate: Optional[float] = 1.0
    pitch: Optional[float] = 1.0

# --- Book Routes ---
@router.post("/books")
async def upload_book(file: UploadFile = File(...)):
    """上传新书籍"""
    if not file.filename.endswith(".epub"):
        raise HTTPException(status_code=400, detail="Only EPUB files are supported")
    
    book_id = await BookService.save_upload(file)
    meta_info = BookService.parse_metadata(book_id)
    toc = BookService.get_toc(book_id)
    
    # 添加到书架
    cover_url = meta_info["coverUrl"]
    if cover_url:
        cover_url = f"http://localhost:8000{cover_url}"
    BookLibrary.add_book(book_id, meta_info["metadata"], cover_url)
    
    return {
        "bookId": book_id,
        "metadata": meta_info["metadata"],
        "coverUrl": meta_info["coverUrl"],
        "toc": toc
    }

@router.get("/books")
async def list_books():
    """获取书架上所有书籍"""
    return BookLibrary.get_all_books()

@router.get("/books/{book_id}")
async def get_book(book_id: str):
    """获取单本书的完整信息（用于打开已有书籍）"""
    book_info = BookLibrary.get_book(book_id)
    if not book_info:
        raise HTTPException(status_code=404, detail="Book not found in library")
    
    # 检查文件是否存在
    if not os.path.exists(BookService.get_book_path(book_id)):
        # 文件不存在，从书架删除
        BookLibrary.delete_book(book_id)
        raise HTTPException(status_code=404, detail="Book file not found")
    
    # 更新最后打开时间
    BookLibrary.update_last_opened(book_id)
    
    # 获取完整信息
    meta_info = BookService.parse_metadata(book_id)
    toc = BookService.get_toc(book_id)
    
    return {
        "bookId": book_id,
        "metadata": meta_info["metadata"],
        "coverUrl": meta_info["coverUrl"],
        "toc": toc
    }

@router.delete("/books/{book_id}")
async def delete_book(book_id: str):
    """从书架删除书籍"""
    # 删除文件
    book_path = BookService.get_book_path(book_id)
    if os.path.exists(book_path):
        os.remove(book_path)
    
    # 从索引删除
    deleted = BookLibrary.delete_book(book_id)
    
    if deleted:
        return {"message": "书籍已删除", "bookId": book_id}
    else:
        raise HTTPException(status_code=404, detail="Book not found")

@router.get("/books/{book_id}/chapters")
async def get_chapter(book_id: str, href: str):
    """获取章节内容"""
    return BookService.get_chapter_content(book_id, href)

# --- TTS Routes ---
@router.post("/tts/speak")
async def speak(request: TTSRequest):
    """
    文字转语音接口
    - 如果缓存中存在相同参数的音频，直接返回缓存
    - 否则生成新音频并缓存
    返回: {"audioUrl": str, "cached": bool, "wordTimestamps": [...]}
    """
    print(f"[API] TTS request: text='{request.text[:100] if request.text else 'EMPTY'}...', voice={request.voice}")
    
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    try:
        result = await TTSService.generate_audio(
            text=request.text, 
            voice=request.voice, 
            rate=request.rate, 
            pitch=request.pitch
        )
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tts/voices")
async def get_voices(lang: str = None):
    """
    获取可用语音列表
    - lang: 可选，按语言筛选，如 "zh", "en", "ja"
    """
    voices = await TTSService.get_voices()
    if lang:
        voices = [v for v in voices if v["lang"].lower().startswith(lang.lower())]
    return voices

@router.get("/tts/voices/chinese")
async def get_chinese_voices():
    """
    获取所有中文语音（包含普通话、粤语、台湾腔）
    """
    voices = await TTSService.get_voices()
    chinese_voices = [v for v in voices if v["lang"].startswith("zh")]
    
    # 添加友好的显示名称
    display_names = {
        "zh-CN-XiaoxiaoNeural": "晓晓（活泼女声）⭐",
        "zh-CN-XiaoyiNeural": "晓伊（温柔女声）",
        "zh-CN-YunjianNeural": "云健（成熟男声）",
        "zh-CN-YunxiNeural": "云希（年轻男声）⭐",
        "zh-CN-YunxiaNeural": "云夏（少年音）",
        "zh-CN-YunyangNeural": "云扬（新闻播报）",
        "zh-CN-liaoning-XiaobeiNeural": "晓北（东北话）",
        "zh-CN-shaanxi-XiaoniNeural": "晓妮（陕西话）",
        "zh-HK-HiuGaaiNeural": "曉佳（粤语女声）",
        "zh-HK-HiuMaanNeural": "曉曼（粤语女声）",
        "zh-HK-WanLungNeural": "雲龍（粤语男声）",
        "zh-TW-HsiaoChenNeural": "曉臻（台湾女声）",
        "zh-TW-HsiaoYuNeural": "曉雨（台湾女声）",
        "zh-TW-YunJheNeural": "雲哲（台湾男声）",
    }
    
    # 分类排序：普通话优先，然后粤语，最后台湾
    def sort_key(v):
        name = v["name"]
        if "zh-CN-liaoning" in name or "zh-CN-shaanxi" in name:
            return (1, name)  # 方言
        elif name.startswith("zh-CN"):
            return (0, name)  # 普通话
        elif name.startswith("zh-HK"):
            return (2, name)  # 粤语
        else:
            return (3, name)  # 台湾
    
    chinese_voices.sort(key=sort_key)
    
    result = []
    for v in chinese_voices:
        result.append({
            "name": v["name"],
            "displayName": display_names.get(v["name"], v["name"]),
            "gender": v["gender"],
            "lang": v["lang"]
        })
    
    return result

# --- 缓存管理 Routes ---
@router.get("/tts/cache/stats")
async def get_cache_stats():
    """获取音频缓存统计信息"""
    return AudioCache.get_cache_stats()

@router.delete("/tts/cache")
async def clear_cache():
    """清空音频缓存"""
    count = AudioCache.clear_cache()
    return {"message": f"已清除 {count} 个缓存文件", "cleared_count": count}

# --- 下载音频 Routes ---
@router.post("/tts/download")
async def download_chapter_audio(request: DownloadRequest):
    """
    合成整个章节的音频并返回下载链接
    将多个句子合并成一个音频文件
    """
    if not request.sentences or len(request.sentences) == 0:
        raise HTTPException(status_code=400, detail="No sentences provided")
    
    # 过滤空句子
    sentences = [s.strip() for s in request.sentences if s and s.strip()]
    if not sentences:
        raise HTTPException(status_code=400, detail="All sentences are empty")
    
    print(f"[API] Download request: {len(sentences)} sentences, voice={request.voice}")
    
    try:
        # 合并所有句子，用换行分隔（让语音有自然停顿）
        full_text = "\n".join(sentences)
        
        # 生成音频
        result = await TTSService.generate_chapter_audio(
            text=full_text,
            voice=request.voice,
            rate=request.rate,
            pitch=request.pitch,
            filename=request.filename
        )
        
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tts/download/{filename}")
async def get_download_file(filename: str):
    """
    获取已生成的音频文件用于下载
    """
    filepath = os.path.join("data/audio", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    # 返回文件供下载
    return FileResponse(
        filepath,
        media_type="audio/mpeg",
        filename=filename
    )

@router.post("/books/{book_id}/download-audio")
async def download_book_audio(book_id: str, request: BookDownloadRequest):
    """
    创建后台任务生成整本书的音频（支持断点续传）
    返回任务ID，可通过 /api/tasks/{task_id} 查询进度
    """
    import time as time_module
    
    # 检查书籍是否存在
    book_path = BookService.get_book_path(book_id)
    if not os.path.exists(book_path):
        raise HTTPException(status_code=404, detail="Book not found")
    
    # 获取书籍信息
    book_info = BookLibrary.get_book(book_id)
    book_title = book_info.get("title", "book") if book_info else "book"
    
    # 检查是否有可恢复的任务（同一本书、失败或中断的任务）
    existing_tasks = task_manager.get_all_tasks()
    resumable_task = None
    for task in existing_tasks:
        if (task.get("type") == "book_audio" and 
            task.get("params", {}).get("book_id") == book_id and
            task.get("status") == "failed" and
            task.get("params", {}).get("output_filepath") and
            task.get("params", {}).get("processed_chapters", 0) > 0):
            # 检查部分文件是否存在
            partial_file = task.get("params", {}).get("output_filepath")
            if os.path.exists(partial_file):
                resumable_task = task
                break
    
    if resumable_task:
        # 恢复之前的任务
        task_id = resumable_task["id"]
        resume_from = resumable_task["params"].get("processed_chapters", 0)
        output_filepath = resumable_task["params"]["output_filepath"]
        output_filename = os.path.basename(output_filepath)
        
        # 重置任务状态
        task_manager.update_task(
            task_id,
            status=TaskStatus.PENDING,
            progress=0,
            progressText="准备恢复下载...",
            error=None
        )
        is_resume = True
    else:
        # 创建新任务
        timestamp = int(time_module.time())
        safe_filename = "".join(c for c in book_title if c.isalnum() or c in "._- ").strip()
        if not safe_filename:
            safe_filename = "book"
        output_filename = f"{safe_filename}_{timestamp}.mp3"
        output_filepath = os.path.join(AUDIO_DIR, output_filename)
        resume_from = 0
        
        task_id = task_manager.create_task(
            task_type="book_audio",
            params={
                "book_id": book_id,
                "voice": request.voice,
                "rate": request.rate,
                "pitch": request.pitch,
                "output_filepath": output_filepath,
                "processed_chapters": 0
            },
            title=f"生成《{book_title}》音频"
        )
        is_resume = False
    
    # 启动后台任务（使用外部作用域的变量：output_filepath, resume_from, is_resume）
    async def generate_book_audio_task():
        nonlocal output_filepath, resume_from, is_resume, output_filename
        
        try:
            task_manager.start_task(task_id)
            
            if is_resume:
                task_manager.update_progress(task_id, 2, f"恢复下载，跳过前 {resume_from} 章...")
            else:
                task_manager.update_progress(task_id, 2, "正在读取书籍目录...")
            
            # 获取目录
            toc = BookService.get_toc(book_id)
            if not toc:
                raise Exception("Book has no chapters")
            
            # 扁平化收集所有章节信息
            chapters_to_process = []
            
            def collect_chapters(items):
                for item in items:
                    chapters_to_process.append({
                        "href": item.get("href", ""),
                        "label": item.get("label", "")
                    })
                    if item.get("subitems"):
                        collect_chapters(item["subitems"])
            
            collect_chapters(toc)
            total_chapters = len(chapters_to_process)
            
            if total_chapters == 0:
                raise Exception("No chapters found")
            
            if is_resume:
                task_manager.update_progress(task_id, 5, f"共 {total_chapters} 章，从第 {resume_from + 1} 章继续...")
            else:
                task_manager.update_progress(task_id, 5, f"共 {total_chapters} 章节，开始逐章生成音频...")
            
            # Rate & Pitch 格式化
            rate_pct = int((request.rate - 1.0) * 100)
            rate_str = f"{rate_pct:+d}%"
            pitch_hz = int((request.pitch - 1.0) * 50)
            pitch_str = f"{pitch_hz:+d}Hz"
            
            # 打开文件（续传用追加模式，新建用写入模式）
            processed = resume_from
            has_audio = is_resume  # 如果是续传，说明已有音频
            file_mode = 'ab' if is_resume else 'wb'
            
            with open(output_filepath, file_mode) as audio_file:
                for idx, chapter_info in enumerate(chapters_to_process):
                    # 跳过已处理的章节
                    if idx < resume_from:
                        continue
                    try:
                        # 获取章节内容
                        chapter = BookService.get_chapter_content(book_id, chapter_info["href"])
                        raw_text = chapter.get("text", "").strip()
                        
                        if not raw_text:
                            processed += 1
                            continue
                        
                        # 添加章节标题
                        chapter_title = chapter_info["label"]
                        if chapter_title:
                            full_chapter_text = f"{chapter_title}。\n{raw_text}"
                        else:
                            full_chapter_text = raw_text
                        
                        # 语言检测
                        detected_lang = TTSService.detect_language(full_chapter_text)
                        voice_lang = request.voice.split("-")[0].lower() if request.voice else ""
                        voice = request.voice
                        if voice_lang != detected_lang:
                            voice = TTSService.get_default_voice(full_chapter_text)
                        
                        # 生成这一章的音频，直接写入文件
                        communicate = edge_tts.Communicate(full_chapter_text, voice, rate=rate_str, pitch=pitch_str)
                        
                        async for chunk in communicate.stream():
                            if chunk["type"] == "audio":
                                audio_file.write(chunk["data"])
                                has_audio = True
                        
                        # 每章完成后刷新到磁盘
                        audio_file.flush()
                        
                    except Exception as e:
                        print(f"[Task] Skip chapter {chapter_info['href']}: {e}")
                    
                    processed += 1
                    # 进度：5% - 95% 用于生成音频
                    progress = 5 + int((processed / total_chapters) * 90)
                    task_manager.update_progress(
                        task_id, progress, 
                        f"已完成 {processed}/{total_chapters} 章节"
                    )
                    
                    # 保存已处理章节数（用于断点续传）
                    task_manager.update_task(
                        task_id,
                        params={
                            "book_id": book_id,
                            "voice": request.voice,
                            "rate": request.rate,
                            "pitch": request.pitch,
                            "output_filepath": output_filepath,
                            "processed_chapters": processed
                        }
                    )
            
            if not has_audio:
                # 删除空文件
                if os.path.exists(output_filepath):
                    os.remove(output_filepath)
                raise Exception("No audio generated")
            
            file_size = os.path.getsize(output_filepath)
            
            task_manager.complete_task(task_id, {
                "downloadUrl": f"/api/tts/download/{output_filename}",
                "filename": output_filename,
                "size": file_size,
                "bookTitle": book_title,
                "totalChapters": total_chapters
            })
            
        except asyncio.CancelledError:
            task_manager.fail_task(task_id, "任务已取消")
        except Exception as e:
            import traceback
            traceback.print_exc()
            task_manager.fail_task(task_id, str(e))
        finally:
            task_manager.unregister_running_task(task_id)
    
    # 启动后台任务
    task = asyncio.create_task(generate_book_audio_task())
    task_manager.register_running_task(task_id, task)
    
    if is_resume:
        return {
            "taskId": task_id,
            "message": f"恢复下载《{book_title}》，从第 {resume_from + 1} 章继续",
            "bookTitle": book_title,
            "resumed": True,
            "resumeFrom": resume_from
        }
    else:
        return {
            "taskId": task_id,
            "message": f"任务已创建，正在后台生成《{book_title}》的音频",
            "bookTitle": book_title,
            "resumed": False
        }

# --- 任务管理 Routes ---
@router.get("/tasks")
async def list_tasks():
    """获取所有任务列表"""
    return task_manager.get_all_tasks()

@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取单个任务的状态"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    deleted = task_manager.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "任务已删除", "taskId": task_id}
