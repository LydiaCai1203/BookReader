import edge_tts
import hashlib
import json
import os
import re
from typing import List, Dict, Optional, Any
from datetime import datetime

AUDIO_DIR = "data/audio"
CACHE_INDEX_FILE = "data/audio/cache_index.json"


class AudioCache:
    """音频缓存管理器"""
    
    @staticmethod
    def _load_index() -> Dict:
        """加载缓存索引"""
        if os.path.exists(CACHE_INDEX_FILE):
            try:
                with open(CACHE_INDEX_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    @staticmethod
    def _save_index(index: Dict) -> None:
        """保存缓存索引"""
        os.makedirs(os.path.dirname(CACHE_INDEX_FILE), exist_ok=True)
        with open(CACHE_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def generate_cache_key(text: str, voice: str, rate: float, pitch: float) -> str:
        """生成缓存键（基于文本和参数的哈希）"""
        content = f"{text}|{voice}|{rate}|{pitch}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    @staticmethod
    def get_cached_entry(cache_key: str) -> Optional[Dict]:
        """获取缓存条目（包含音频URL和时间戳）"""
        index = AudioCache._load_index()
        if cache_key in index:
            entry = index[cache_key]
            filepath = os.path.join(AUDIO_DIR, entry['filename'])
            if os.path.exists(filepath):
                # 更新访问时间
                entry['last_accessed'] = datetime.now().isoformat()
                index[cache_key] = entry
                AudioCache._save_index(index)
                return entry
        return None
    
    @staticmethod
    def save_to_cache(
        cache_key: str, 
        filename: str, 
        text: str, 
        voice: str, 
        rate: float, 
        pitch: float,
        word_timestamps: List[Dict] = None
    ) -> None:
        """保存音频和时间戳到缓存"""
        index = AudioCache._load_index()
        index[cache_key] = {
            'filename': filename,
            'text_preview': text[:100] + '...' if len(text) > 100 else text,
            'voice': voice,
            'rate': rate,
            'pitch': pitch,
            'word_timestamps': word_timestamps or [],
            'created_at': datetime.now().isoformat(),
            'last_accessed': datetime.now().isoformat()
        }
        AudioCache._save_index(index)
    
    @staticmethod
    def get_cache_stats() -> Dict:
        """获取缓存统计信息"""
        index = AudioCache._load_index()
        total_size = 0
        for entry in index.values():
            filepath = os.path.join(AUDIO_DIR, entry['filename'])
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
        
        return {
            'total_entries': len(index),
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'entries': list(index.values())
        }
    
    @staticmethod
    def clear_cache() -> int:
        """清空缓存，返回清除的文件数"""
        index = AudioCache._load_index()
        count = 0
        for entry in index.values():
            filepath = os.path.join(AUDIO_DIR, entry['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
                count += 1
        # 清空索引
        AudioCache._save_index({})
        return count


class TTSService:
    # 默认语音映射
    DEFAULT_VOICES = {
        "zh": "zh-CN-XiaoxiaoNeural",    # 中文
        "en": "en-US-JennyNeural",        # 英文
        "ja": "ja-JP-NanamiNeural",       # 日文
        "ko": "ko-KR-SunHiNeural",        # 韩文
    }
    
    @staticmethod
    def detect_language(text: str) -> str:
        """简单的语言检测"""
        # 检查是否包含中文字符
        if re.search(r'[\u4e00-\u9fff]', text):
            return "zh"
        # 检查是否包含日文字符
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
            return "ja"
        # 检查是否包含韩文字符
        if re.search(r'[\uac00-\ud7af]', text):
            return "ko"
        # 默认英文
        return "en"
    
    @staticmethod
    def get_default_voice(text: str) -> str:
        """根据文本内容获取合适的默认语音"""
        lang = TTSService.detect_language(text)
        return TTSService.DEFAULT_VOICES.get(lang, "en-US-JennyNeural")
    
    @staticmethod
    async def get_voices() -> List[Dict[str, str]]:
        voices = await edge_tts.list_voices()
        # Format for frontend
        return [
            {
                "name": v["ShortName"],
                "gender": v["Gender"],
                "lang": v["Locale"]
            }
            for v in voices
        ]

    @staticmethod
    async def generate_audio(text: str, voice: str, rate: float = 1.0, pitch: float = 1.0) -> Dict[str, Any]:
        """
        生成音频，优先从缓存获取
        返回: {
            "audioUrl": str, 
            "cached": bool,
            "wordTimestamps": [{"text": str, "offset": int, "duration": int}, ...]
        }
        offset 和 duration 单位为毫秒
        """
        # 确保音频目录存在
        os.makedirs(AUDIO_DIR, exist_ok=True)
        
        # 检查文本是否为空
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        # 如果语音和文本语言不匹配，自动选择合适的语音
        detected_lang = TTSService.detect_language(text)
        voice_lang = voice.split("-")[0].lower() if voice else ""
        
        if voice_lang != detected_lang:
            suggested_voice = TTSService.get_default_voice(text)
            print(f"[TTS] Language mismatch: text is '{detected_lang}', voice is '{voice_lang}'. Using '{suggested_voice}' instead.")
            voice = suggested_voice
        
        # 检查缓存（使用最终确定的 voice）
        cache_key = AudioCache.generate_cache_key(text, voice, rate, pitch)
        cached_entry = AudioCache.get_cached_entry(cache_key)
        
        if cached_entry:
            return {
                "audioUrl": f"/audio/{cached_entry['filename']}", 
                "cached": True,
                "wordTimestamps": cached_entry.get('word_timestamps', [])
            }
        
        # 缓存未命中，生成新音频
        # Rate string format: "+50%" or "-20%"
        rate_pct = int((rate - 1.0) * 100)
        rate_str = f"{rate_pct:+d}%"
        
        # Pitch string format: "+0Hz" or "+10Hz"
        pitch_hz = int((pitch - 1.0) * 50)
        pitch_str = f"{pitch_hz:+d}Hz"
        
        print(f"[TTS] Generating audio: text='{text[:50]}...', voice={voice}, rate={rate_str}, pitch={pitch_str}")
        
        communicate = edge_tts.Communicate(text, voice, rate=rate_str, pitch=pitch_str)
        
        # 使用缓存键作为文件名
        filename = f"{cache_key}.mp3"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        # 收集单词时间戳和音频数据
        word_timestamps = []
        audio_chunks = []
        
        try:
            async for chunk in communicate.stream():
                chunk_type = chunk.get("type", "")
                
                if chunk_type == "audio":
                    audio_chunks.append(chunk.get("data", b""))
                elif chunk_type == "WordBoundary":
                    # edge-tts 返回的时间单位是 100纳秒 (ticks)，转换为毫秒
                    # 兼容不同版本的字段名
                    offset = chunk.get("offset", 0)
                    duration = chunk.get("duration", 0)
                    word_text = chunk.get("text", "")
                    
                    # 转换为毫秒 (100纳秒 = 0.0001毫秒)
                    offset_ms = offset // 10000 if offset else 0
                    duration_ms = duration // 10000 if duration else 0
                    
                    if word_text:
                        word_timestamps.append({
                            "text": word_text,
                            "offset": offset_ms,
                            "duration": duration_ms
                        })
        except Exception as e:
            print(f"[TTS] Stream error: {e}")
            # 如果流式处理失败，创建新的 Communicate 对象重试
            try:
                communicate_retry = edge_tts.Communicate(text, voice, rate=rate_str, pitch=pitch_str)
                await communicate_retry.save(filepath)
                AudioCache.save_to_cache(
                    cache_key, filename, text, voice, rate, pitch, []
                )
                return {
                    "audioUrl": f"/audio/{filename}", 
                    "cached": False,
                    "wordTimestamps": []
                }
            except Exception as e2:
                print(f"[TTS] Retry also failed: {e2}")
                raise e2
        
        # 写入音频文件
        if audio_chunks:
            with open(filepath, 'wb') as f:
                for chunk in audio_chunks:
                    f.write(chunk)
        else:
            # 如果没有收集到音频块，使用 save 方法
            await communicate.save(filepath)
        
        # 保存到缓存索引（包含时间戳）
        AudioCache.save_to_cache(
            cache_key, filename, text, voice, rate, pitch, word_timestamps
        )
        
        return {
            "audioUrl": f"/audio/{filename}", 
            "cached": False,
            "wordTimestamps": word_timestamps
        }

    @staticmethod
    async def generate_chapter_audio(
        text: str, 
        voice: str, 
        rate: float = 1.0, 
        pitch: float = 1.0,
        filename: str = "chapter",
        progress_callback: callable = None
    ) -> Dict[str, Any]:
        """
        生成整个章节的音频文件（用于下载）
        不使用缓存，每次生成新文件
        progress_callback: 可选的进度回调函数 (progress: int, text: str) -> None
        返回: {"downloadUrl": str, "filename": str, "size": int}
        """
        import time
        
        # 确保音频目录存在
        os.makedirs(AUDIO_DIR, exist_ok=True)
        
        # 检查文本是否为空
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        # 自动语言检测
        detected_lang = TTSService.detect_language(text)
        voice_lang = voice.split("-")[0].lower() if voice else ""
        
        if voice_lang != detected_lang:
            suggested_voice = TTSService.get_default_voice(text)
            print(f"[TTS Download] Language mismatch, using '{suggested_voice}'")
            voice = suggested_voice
        
        # Rate string format
        rate_pct = int((rate - 1.0) * 100)
        rate_str = f"{rate_pct:+d}%"
        
        # Pitch string format
        pitch_hz = int((pitch - 1.0) * 50)
        pitch_str = f"{pitch_hz:+d}Hz"
        
        # 使用时间戳生成唯一文件名
        timestamp = int(time.time())
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
        if not safe_filename:
            safe_filename = "chapter"
        output_filename = f"{safe_filename}_{timestamp}.mp3"
        filepath = os.path.join(AUDIO_DIR, output_filename)
        
        text_len = len(text)
        print(f"[TTS Download] Generating: {text_len} chars, voice={voice}")
        
        if progress_callback:
            progress_callback(45, f"开始生成音频 ({text_len} 字符)...")
        
        communicate = edge_tts.Communicate(text, voice, rate=rate_str, pitch=pitch_str)
        
        try:
            # 使用 stream() 获取进度
            audio_chunks = []
            chunk_count = 0
            last_progress_update = time.time()
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])
                    chunk_count += 1
                    
                    # 每秒更新一次进度
                    now = time.time()
                    if progress_callback and (now - last_progress_update) >= 1.0:
                        # 基于音频块数量估算进度 (45-95%)
                        # 假设每秒语音约需要 10-20 个音频块
                        estimated_total_chunks = text_len / 10  # 粗略估计
                        progress = min(95, 45 + int((chunk_count / max(estimated_total_chunks, 1)) * 50))
                        progress_callback(progress, f"生成音频中... ({chunk_count} 块)")
                        last_progress_update = now
            
            # 写入文件
            if progress_callback:
                progress_callback(96, "写入文件...")
            
            with open(filepath, 'wb') as f:
                for chunk in audio_chunks:
                    f.write(chunk)
                    
        except Exception as e:
            print(f"[TTS Download] Error: {e}")
            raise e
        
        # 获取文件大小
        file_size = os.path.getsize(filepath)
        
        if progress_callback:
            progress_callback(100, "完成")
        
        return {
            "downloadUrl": f"/api/tts/download/{output_filename}",
            "filename": output_filename,
            "size": file_size,
            "sizeFormatted": f"{file_size / (1024*1024):.2f} MB"
        }
