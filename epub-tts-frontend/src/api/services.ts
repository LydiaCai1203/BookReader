/**
 * 真实 API 服务 - 连接后端
 */
import type { IBookService, ITTSService, TTSOptions, TTSResponse, ChapterContent, BookMetadata, NavItem, WordTimestamp } from "./types";

const API_BASE = "http://localhost:8000/api";

export class BookService implements IBookService {
  async uploadBook(file: File): Promise<{ bookId: string; metadata: BookMetadata; toc: NavItem[]; coverUrl?: string }> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE}/books`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(error.detail || "Upload failed");
    }

    const data = await response.json();
    return {
      bookId: data.bookId,
      metadata: data.metadata,
      toc: data.toc,
      coverUrl: data.coverUrl ? `http://localhost:8000${data.coverUrl}` : undefined,
    };
  }

  async getChapter(bookId: string, href: string): Promise<ChapterContent> {
    const response = await fetch(
      `${API_BASE}/books/${bookId}/chapters?href=${encodeURIComponent(href)}`
    );

    if (!response.ok) {
      throw new Error("Failed to load chapter");
    }

    return response.json();
  }
}

export class TTSService implements ITTSService {
  private audio: HTMLAudioElement | null = null;
  private currentResolve: (() => void) | null = null;
  private timeUpdateCallback: ((time: number) => void) | null = null;
  private timestampsReadyCallback: ((timestamps: WordTimestamp[]) => void) | null = null;
  private _currentWordTimestamps: WordTimestamp[] = [];

  async getVoices(): Promise<{ name: string; lang: string; gender?: string }[]> {
    const response = await fetch(`${API_BASE}/tts/voices`);
    if (!response.ok) {
      throw new Error("Failed to get voices");
    }
    return response.json();
  }

  /**
   * 设置时间更新回调，用于字词高亮同步
   */
  onTimeUpdate(callback: ((time: number) => void) | null): void {
    this.timeUpdateCallback = callback;
  }

  /**
   * 设置时间戳就绪回调，在音频开始播放时立即调用
   */
  onTimestampsReady(callback: ((timestamps: WordTimestamp[]) => void) | null): void {
    this.timestampsReadyCallback = callback;
  }

  /**
   * 获取当前播放的字词时间戳
   */
  get currentWordTimestamps(): WordTimestamp[] {
    return this._currentWordTimestamps;
  }

  /**
   * 获取当前播放时间（毫秒）
   */
  getCurrentTime(): number {
    return this.audio ? this.audio.currentTime * 1000 : 0;
  }

  async speak(text: string, options?: TTSOptions): Promise<TTSResponse> {
    // 停止当前播放
    this.stop();

    const response = await fetch(`${API_BASE}/tts/speak`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text,
        voice: options?.voice || "en-US-ChristopherNeural",
        rate: options?.rate || 1.0,
        pitch: options?.pitch || 1.0,
        volume: options?.volume || 1.0,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "TTS failed" }));
      throw new Error(error.detail || "TTS failed");
    }

    const data = await response.json();
    const audioUrl = `http://localhost:8000${data.audioUrl}`;
    const wordTimestamps: WordTimestamp[] = data.wordTimestamps || [];
    
    // 保存时间戳供外部使用
    this._currentWordTimestamps = wordTimestamps;
    
    // 立即通知时间戳就绪（在开始播放前）
    if (this.timestampsReadyCallback) {
      this.timestampsReadyCallback(wordTimestamps);
    }
    
    // 创建并播放音频
    return new Promise((resolve, reject) => {
      this.audio = new Audio(audioUrl);
      this.currentResolve = () => resolve({
        audioUrl,
        cached: data.cached,
        wordTimestamps,
      });

      // 时间更新事件 - 用于字词高亮（约 250ms 一次）
      this.audio.ontimeupdate = () => {
        if (this.audio && this.timeUpdateCallback) {
          this.timeUpdateCallback(this.audio.currentTime * 1000);
        }
      };

      this.audio.onended = () => {
        if (this.currentResolve) {
          this.currentResolve();
          this.currentResolve = null;
        }
      };

      this.audio.onerror = () => {
        reject(new Error("Audio playback failed"));
      };

      this.audio.play().catch(reject);
    });
  }

  stop(): void {
    if (this.audio) {
      // 先移除所有事件监听器，防止触发回调
      this.audio.ontimeupdate = null;
      this.audio.onended = null;
      this.audio.onerror = null;
      this.audio.onloadeddata = null;
      
      // 暂停并重置
      this.audio.pause();
      this.audio.currentTime = 0;
      
      // 移除 src 并加载空内容，彻底停止
      this.audio.src = "";
      this.audio.load();
      
      this.audio = null;
    }
    
    // 清除 resolve 回调（不要调用它，让 promise 保持 pending）
    this.currentResolve = null;
    this._currentWordTimestamps = [];
  }
}

