import { useState, useEffect, useCallback } from "react";
import { UploadZone } from "@/components/player/UploadZone";
import { Sidebar } from "@/components/player/Sidebar";
import { Reader } from "@/components/player/Reader";
import { Controls } from "@/components/player/Controls";
import { TranslationSettings } from "@/components/player/TranslationSettings";
import { useUploadBook, useChapter } from "@/hooks/use-book";
import { ttsService } from "@/api";
import type { NavItem, WordTimestamp } from "@/api/types";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable";
import { Button } from "@/components/ui/button";
import { Loader2, Menu, X, BrainCircuit, Languages, Github } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { toast } from "sonner";
import { useIsMobile } from "@/hooks/use-mobile";
import { translator, type TranslatorConfig, DEFAULT_CONFIG } from "@/lib/translator";
import { TTSService } from "@/api/services";
import { TasksPanel } from "@/components/player/TasksPanel";
import { API_BASE, API_URL } from "@/config";

export default function Home() {
  // Book State
  const [bookId, setBookId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<any>({});
  const [toc, setToc] = useState<NavItem[]>([]);
  const [cover, setCover] = useState<string>("");
  
  // Reader State
  const [currentChapterHref, setCurrentChapterHref] = useState<string | null>(null);
  const [currentSentenceIndex, setCurrentSentenceIndex] = useState(0);
  const [displayedSentences, setDisplayedSentences] = useState<string[]>([]);
  
  // Player State
  const [isPlaying, setIsPlaying] = useState(false);
  const [voice, setVoice] = useState<string | null>(null);
  const [speed, setSpeed] = useState(1.0);
  const [emotion, setEmotion] = useState<"neutral" | "warm" | "excited" | "serious" | "suspense">("neutral");
  
  // 字词同步高亮状态
  const [wordTimestamps, setWordTimestamps] = useState<WordTimestamp[]>([]);
  const [currentTime, setCurrentTime] = useState(0);

  // Translation State
  const [transConfig, setTransConfig] = useState<TranslatorConfig>(() => {
    const saved = localStorage.getItem("epub-tts-trans-config");
    return saved ? JSON.parse(saved) : DEFAULT_CONFIG;
  });
  const [translatedCache, setTranslatedCache] = useState<Record<string, string[]>>({});
  const [isTranslating, setIsTranslating] = useState(false);

  const isMobile = useIsMobile();

  // Queries
  const uploadMutation = useUploadBook();
  const { data: chapterData, isLoading: isChapterLoading } = useChapter(bookId, currentChapterHref);

  // Sync translator config
  useEffect(() => {
    translator.updateConfig(transConfig);
  }, [transConfig]);

  // Handle Translation or Raw Content Update
  useEffect(() => {
    if (!chapterData) return;
    
    const href = chapterData.href;
    const rawSentences = chapterData.sentences;

    const processContent = async () => {
        // If translation is enabled
        if (transConfig.enabled && transConfig.apiKey) {
            // Check cache
            if (translatedCache[href]) {
                setDisplayedSentences(translatedCache[href]);
                return;
            }

            // Translate
            setIsTranslating(true);
            try {
                // Join for context, limit length if needed
                const fullText = rawSentences.join(" ");
                // Ideally backend/service handles this, but here we do client-side AI call
                const translatedText = await translator.translate(fullText);
                
                // Simple split for now (should match sentence count ideally, but hard)
                // Re-using a simple splitter
                const newSentences = translatedText.match(/([^.!?。！？\n\r]+[.!?。！？\n\r]+)|([^.!?。！？\n\r]+$)/g)
                    ?.map(s => s.trim())
                    .filter(s => s.length > 0) || [translatedText];

                setTranslatedCache(prev => ({ ...prev, [href]: newSentences }));
                setDisplayedSentences(newSentences);
                toast.success("Chapter Translated");
            } catch (error) {
                console.error("Translation failed", error);
                toast.error("Translation Failed, showing original");
                setDisplayedSentences(rawSentences);
            } finally {
                setIsTranslating(false);
            }
        } else {
            // Raw
            setDisplayedSentences(rawSentences);
        }
    };

    processContent();
  }, [chapterData, transConfig.enabled, transConfig.apiKey, translatedCache]);


  const handleConfigChange = (newConfig: TranslatorConfig) => {
    setTransConfig(newConfig);
    localStorage.setItem("epub-tts-trans-config", JSON.stringify(newConfig));
    toast.success("Settings Saved");
  };

  const handleFileSelect = (file: File) => {
    toast.promise(uploadMutation.mutateAsync(file), {
      loading: '正在上传并解析书籍...',
      success: (data) => {
         setBookId(data.bookId);
         setMetadata(data.metadata);
         setToc(data.toc);
         if (data.coverUrl) setCover(data.coverUrl);
         
         if (data.toc.length > 0) {
            setCurrentChapterHref(data.toc[0].href);
         }
         return "书籍已就绪";
      },
      error: "加载失败"
    });
  };

  // 从书架选择已有书籍
  const handleBookSelect = async (bookId: string) => {
    toast.promise(
      fetch(`${API_URL}/books/${bookId}`).then(res => {
        if (!res.ok) throw new Error("Failed to load book");
        return res.json();
      }),
      {
        loading: '正在加载书籍...',
        success: (data) => {
          setBookId(data.bookId);
          setMetadata(data.metadata);
          setToc(data.toc);
          if (data.coverUrl) setCover(`${API_BASE}${data.coverUrl}`);
          
          if (data.toc.length > 0) {
            setCurrentChapterHref(data.toc[0].href);
          }
          return `已打开《${data.metadata?.title || '书籍'}》`;
        },
        error: "加载失败，书籍可能已被删除"
      }
    );
  };

  const handleDemoSelect = async () => {
    // Mock Demo Data
    const mockId = "demo-book";
    setBookId(mockId);
    setMetadata({ title: "The Neural Horizon (Demo)", creator: "AnyGen AI" });
    setToc([
        { id: "1", href: "chapter1", label: "Chapter 1: Awakening" },
        { id: "2", href: "chapter2", label: "Chapter 2: The Signal" }
    ]);
    setCurrentChapterHref("chapter1");
    // Note: The useChapter hook needs to handle this mock ID in the service layer
    // We assume MockBookService handles 'demo-book' id or we manually feed data?
    // Actually, MockBookService.getChapter needs to know about "demo-book"
    // See next step to ensure MockBookService has demo data.
  };

  // 时间更新回调
  const handleTimeUpdate = useCallback((time: number) => {
    setCurrentTime(time);
  }, []);

  // 时间戳就绪回调
  const handleTimestampsReady = useCallback((timestamps: WordTimestamp[]) => {
    setWordTimestamps(timestamps);
  }, []);

  // 注册/注销回调
  useEffect(() => {
    const service = ttsService as TTSService;
    if (service.onTimeUpdate) {
      service.onTimeUpdate(handleTimeUpdate);
    }
    if (service.onTimestampsReady) {
      service.onTimestampsReady(handleTimestampsReady);
    }
    return () => {
      if (service.onTimeUpdate) {
        service.onTimeUpdate(null);
      }
      if (service.onTimestampsReady) {
        service.onTimestampsReady(null);
      }
    };
  }, [handleTimeUpdate, handleTimestampsReady]);

  // TTS Loop
  useEffect(() => {
    // 用于标记当前 effect 是否已被取消
    let cancelled = false;
    
    if (!isPlaying) {
       ttsService.stop();
       setWordTimestamps([]);
       setCurrentTime(0);
       return;
    }

    if (currentSentenceIndex >= displayedSentences.length) {
       setIsPlaying(false);
       return;
    }

    const text = displayedSentences[currentSentenceIndex];
    if (!text) return;
    
    const getEmotionParams = (e: string) => {
       switch(e) {
          case "warm": return { rate: 0.9 * speed, pitch: 1.05 };
          case "excited": return { rate: 1.2 * speed, pitch: 1.2 };
          case "serious": return { rate: 0.85 * speed, pitch: 0.8 };
          default: return { rate: 1.0 * speed, pitch: 1.0 };
       }
    };
    
    const params = getEmotionParams(emotion);

    // 先停止之前的音频，再开始新的
    ttsService.stop();
    setCurrentTime(0);
    
    // 开始播放
    ttsService.speak(text, {
      voice: voice || undefined,
      rate: params.rate,
      pitch: params.pitch
    }).then(() => {
      // 如果 effect 已被取消（比如参数变化了），不要进入下一句
      if (cancelled) return;
      
      // 播放完成后进入下一句
      if (isPlaying) {
        setWordTimestamps([]);
        setCurrentTime(0);
        setCurrentSentenceIndex(prev => prev + 1);
      }
    }).catch(e => {
      if (cancelled) return;
      console.error(e);
      setIsPlaying(false);
    });
    
    // 清理函数：当 effect 重新运行或组件卸载时调用
    return () => {
      cancelled = true;
      ttsService.stop();
    };
  }, [isPlaying, currentSentenceIndex, displayedSentences, voice, speed, emotion]);


  // Handlers
  const handleNext = () => {
    if (currentSentenceIndex < displayedSentences.length - 1) {
       ttsService.stop();
       setCurrentSentenceIndex(p => p + 1);
    } else {
       // Next Chapter Logic
       const findNext = (items: NavItem[]): string | null => {
          const idx = items.findIndex(i => i.href === currentChapterHref);
          if (idx !== -1 && idx < items.length - 1) return items[idx+1].href;
          return null;
       };
       const nextHref = findNext(toc);
       if (nextHref) {
         setCurrentChapterHref(nextHref);
         setCurrentSentenceIndex(0);
       }
    }
  };
  
  const handlePrev = () => {
     if (currentSentenceIndex > 0) {
        ttsService.stop();
        setCurrentSentenceIndex(p => p - 1);
     }
  };
  
  const togglePlay = () => {
    if (isPlaying) {
      // 暂停时立即停止音频，不等 useEffect
      ttsService.stop();
    }
    setIsPlaying(!isPlaying);
  };


  if (!bookId) {
    return (
      <div className="min-h-screen bg-background text-foreground relative overflow-hidden flex flex-col">
         <div className="absolute top-4 right-4 z-50 flex gap-2">
           <a 
             href="https://github.com/LydiaCai1203/BookReader" 
             target="_blank" 
             rel="noopener noreferrer"
           >
             <Button variant="outline" size="sm" className="border-primary/20 hover:border-primary hover:bg-primary/10">
               <Github className="w-4 h-4" />
             </Button>
           </a>
           <TasksPanel />
           <TranslationSettings config={transConfig} onConfigChange={handleConfigChange} />
         </div>
         <div className="flex-1 flex items-center justify-center">
            <UploadZone 
              onFileSelect={handleFileSelect} 
              onDemoSelect={handleDemoSelect}
              onBookSelect={handleBookSelect}
            />
         </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen bg-background text-foreground flex flex-col overflow-hidden relative">
      <ResizablePanelGroup direction="horizontal" className="flex-1">
        {!isMobile && (
          <>
            <ResizablePanel defaultSize={20} minSize={15} maxSize={30}>
              <Sidebar 
                toc={toc} 
                currentChapterHref={currentChapterHref || ""}
                onSelectChapter={(href) => { 
                   ttsService.stop();  // 立即停止音频
                   setCurrentChapterHref(href); 
                   setCurrentSentenceIndex(0);
                   setIsPlaying(false);
                }}
                coverUrl={cover}
                title={metadata.title}
                bookId={bookId || undefined}
                selectedVoice={voice || undefined}
                speed={speed}
              />
            </ResizablePanel>
            <ResizableHandle />
          </>
        )}
        
        <ResizablePanel defaultSize={80}>
          <div className="h-full flex flex-col relative">
             <div className="absolute top-4 right-4 z-10 flex gap-2">
                 <a 
                   href="https://github.com/LydiaCai1203/BookReader" 
                   target="_blank" 
                   rel="noopener noreferrer"
                 >
                   <Button variant="outline" size="sm" className="bg-background/50 backdrop-blur border-primary/20 hover:border-primary hover:bg-primary/10">
                     <Github className="w-4 h-4" />
                   </Button>
                 </a>
                 <TasksPanel />
                 <TranslationSettings config={transConfig} onConfigChange={handleConfigChange} />
                 <Button variant="outline" size="sm" onClick={() => { ttsService.stop(); setBookId(null); setIsPlaying(false); }} className="bg-background/50 backdrop-blur hover:bg-destructive hover:text-destructive-foreground">
                   退出
                 </Button>
             </div>

             <div className="flex-1 overflow-hidden relative">
                {(isChapterLoading || isTranslating) ? (
                  <div className="absolute inset-0 flex flex-col gap-4 items-center justify-center bg-background/90 backdrop-blur z-20">
                     <div className="relative">
                        <Loader2 className="w-16 h-16 animate-spin text-primary" />
                        {isTranslating && <Languages className="w-6 h-6 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-primary animate-pulse" />}
                     </div>
                     <p className="font-display font-bold text-lg text-primary animate-pulse tracking-widest uppercase">
                        {isTranslating ? "Translating..." : "Loading Data..."}
                     </p>
                  </div>
                ) : null}
                
                <Reader 
                  sentences={displayedSentences} 
                  current={currentSentenceIndex}
                  wordTimestamps={wordTimestamps}
                  currentTime={currentTime}
                  isPlaying={isPlaying}
                />
             </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>

      <Controls 
        isPlaying={isPlaying}
        onPlayPause={togglePlay}
        onNext={handleNext}
        onPrev={handlePrev}
        current={currentSentenceIndex}
        total={displayedSentences.length}
        progress={displayedSentences.length > 0 ? (currentSentenceIndex / displayedSentences.length) * 100 : 0}
        
        selectedVoice={voice}
        onVoiceChange={setVoice}
        emotion={emotion}
        onEmotionChange={(e) => setEmotion(e)}
        speed={speed}
        onSpeedChange={setSpeed}
        
        sentences={displayedSentences}
        chapterTitle={metadata?.title || "chapter"}
      />
    </div>
  );
}
