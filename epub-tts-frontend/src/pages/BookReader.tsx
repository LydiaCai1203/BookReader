import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useLocation } from "wouter";
import { Sidebar } from "@/components/player/Sidebar";
import { Reader } from "@/components/player/Reader";
import { Controls } from "@/components/player/Controls";
import { TranslationSettings } from "@/components/player/TranslationSettings";
import { useChapter } from "@/hooks/use-book";
import { ttsService } from "@/api";
import type { NavItem, WordTimestamp } from "@/api/types";
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from "@/components/ui/resizable";
import { Button } from "@/components/ui/button";
import { Loader2, Menu, X, BrainCircuit, Languages, Home, ArrowLeft } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { toast } from "sonner";
import { useIsMobile } from "@/hooks/use-mobile";
import { translator, type TranslatorConfig, DEFAULT_CONFIG } from "@/lib/translator";
import { TTSService } from "@/api/services";
import { TasksPanel } from "@/components/player/TasksPanel";
import { API_BASE, API_URL } from "@/config";

export default function BookReader() {
  const { bookId } = useParams<{ bookId: string }>();
  const [, navigate] = useLocation();
  
  // Book State
  const [metadata, setMetadata] = useState<any>({});
  const [toc, setToc] = useState<NavItem[]>([]);
  const [cover, setCover] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  
  // Reader State
  const [currentChapterHref, setCurrentChapterHref] = useState<string | null>(null);
  const [currentSentenceIndex, setCurrentSentenceIndex] = useState(0);
  const [displayedSentences, setDisplayedSentences] = useState<string[]>([]);
  
  // Player State
  const [isPlaying, setIsPlaying] = useState(false);
  const isPlayingRef = useRef(false);
  const playingSentenceRef = useRef<number>(-1);
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

  // 移动端侧边栏状态
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isMobile = useIsMobile();

  // Queries
  const { data: chapterData, isLoading: isChapterLoading } = useChapter(bookId || null, currentChapterHref);

  // 加载书籍信息
  useEffect(() => {
    if (!bookId) {
      navigate("/");
      return;
    }
    
    setIsLoading(true);
    fetch(`${API_URL}/books/${bookId}`)
      .then(res => {
        if (!res.ok) throw new Error("Failed to load book");
        return res.json();
      })
      .then(data => {
        setMetadata(data.metadata);
        setToc(data.toc);
        if (data.coverUrl) setCover(`${API_BASE}${data.coverUrl}`);
        
        if (data.toc.length > 0) {
          setCurrentChapterHref(data.toc[0].href);
        }
      })
      .catch(error => {
        console.error("Failed to load book:", error);
        toast.error("加载失败，书籍可能已被删除");
        navigate("/");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [bookId, navigate]);

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
      if (transConfig.enabled && transConfig.apiKey) {
        if (translatedCache[href]) {
          setDisplayedSentences(translatedCache[href]);
          return;
        }

        setIsTranslating(true);
        try {
          const fullText = rawSentences.join(" ");
          const translatedText = await translator.translate(fullText);
          
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

  // 时间更新回调
  const handleTimeUpdate = useCallback((time: number) => {
    setCurrentTime(time);
  }, []);

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

  // 保持 ref 与 state 同步
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  // TTS Loop
  useEffect(() => {
    if (!isPlaying) {
      ttsService.stop();
      playingSentenceRef.current = -1;
      return;
    }

    if (currentSentenceIndex >= displayedSentences.length) {
      setIsPlaying(false);
      playingSentenceRef.current = -1;
      return;
    }

    const text = displayedSentences[currentSentenceIndex];
    if (!text) return;

    const thisSentenceIndex = currentSentenceIndex;
    
    if (playingSentenceRef.current === thisSentenceIndex) {
      return;
    }

    const getEmotionParams = (e: string) => {
      switch(e) {
        case "warm": return { rate: 0.9 * speed, pitch: 1.05 };
        case "excited": return { rate: 1.2 * speed, pitch: 1.2 };
        case "serious": return { rate: 0.85 * speed, pitch: 0.8 };
        default: return { rate: 1.0 * speed, pitch: 1.0 };
      }
    };
    
    const params = getEmotionParams(emotion);

    ttsService.stop();
    playingSentenceRef.current = thisSentenceIndex;
    
    ttsService.speak(text, {
      voice: voice || undefined,
      rate: params.rate,
      pitch: params.pitch,
      book_id: bookId || undefined,
      chapter_href: currentChapterHref || undefined,
      paragraph_index: thisSentenceIndex,
    }).then(() => {
      if (playingSentenceRef.current !== thisSentenceIndex) {
        return;
      }
      
      if (!isPlayingRef.current) {
        playingSentenceRef.current = -1;
        return;
      }
      
      setWordTimestamps([]);
      setCurrentTime(0);
      playingSentenceRef.current = -1;
      setCurrentSentenceIndex(prev => prev + 1);
    }).catch(e => {
      if (playingSentenceRef.current === thisSentenceIndex) {
        console.error("TTS Error:", e);
        playingSentenceRef.current = -1;
        setIsPlaying(false);
      }
    });

  }, [isPlaying, currentSentenceIndex, displayedSentences, voice, speed, emotion, bookId, currentChapterHref]);

  // 章节切换时重置句子索引
  useEffect(() => {
    setCurrentSentenceIndex(0);
    setIsPlaying(false);
    playingSentenceRef.current = -1;
    setWordTimestamps([]);
    setCurrentTime(0);
  }, [currentChapterHref]);

  const togglePlay = () => {
    if (displayedSentences.length === 0) return;
    
    if (isPlaying) {
      ttsService.stop();
      playingSentenceRef.current = -1;
    }
    setIsPlaying(!isPlaying);
  };

  const handleNext = () => {
    if (currentSentenceIndex < displayedSentences.length - 1) {
      ttsService.stop();
      playingSentenceRef.current = -1;
      setWordTimestamps([]);
      setCurrentTime(0);
      setCurrentSentenceIndex(prev => prev + 1);
    }
  };

  const handlePrev = () => {
    if (currentSentenceIndex > 0) {
      ttsService.stop();
      playingSentenceRef.current = -1;
      setWordTimestamps([]);
      setCurrentTime(0);
      setCurrentSentenceIndex(prev => prev - 1);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="h-[100dvh] flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <span className="text-muted-foreground font-mono text-sm">加载中...</span>
        </div>
      </div>
    );
  }

  // Sidebar component
  const sidebarContent = (
    <Sidebar
      toc={toc}
      currentChapterHref={currentChapterHref || ""}
      onSelectChapter={(href) => {
        setCurrentChapterHref(href);
        setMobileMenuOpen(false);
      }}
      coverUrl={cover}
      title={metadata?.title}
      bookId={bookId}
      selectedVoice={voice || undefined}
      speed={speed}
    />
  );

  return (
    <>
    <div className="h-[100dvh] flex flex-col bg-background overflow-hidden pb-[72px]">
      {/* Header */}
      <header className="border-b border-border bg-card/80 backdrop-blur-md py-2 px-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          {/* 返回按钮 */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/")}
            title="返回书架"
          >
            <ArrowLeft className="w-5 h-5" />
          </Button>
          
          {/* 移动端菜单 */}
          {isMobile && (
            <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon">
                  <Menu className="w-5 h-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="p-0 w-72">
                {sidebarContent}
              </SheetContent>
            </Sheet>
          )}
          
          <div className="flex items-center gap-2">
            <BrainCircuit className="w-6 h-6 text-primary" />
            <span className="font-display text-lg font-bold tracking-tight hidden sm:inline">
              {metadata?.title || "BookReader"}
            </span>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <TranslationSettings 
            config={transConfig} 
            onConfigChange={handleConfigChange}
          />
          <TasksPanel />
        </div>
      </header>

      {/* Main Content */}
      {isMobile ? (
        <div className="flex-1 overflow-hidden">
          {isChapterLoading || isTranslating ? (
            <div className="h-full flex items-center justify-center">
              <div className="flex flex-col items-center gap-4 animate-pulse">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
                <span className="text-muted-foreground font-mono text-sm uppercase tracking-wider">
                  {isTranslating ? "Translating..." : "Loading Chapter..."}
                </span>
              </div>
            </div>
          ) : (
            <Reader 
              sentences={displayedSentences} 
              current={currentSentenceIndex}
              wordTimestamps={wordTimestamps}
              currentTime={currentTime}
              isPlaying={isPlaying}
              htmlContent={chapterData?.html}
            />
          )}
        </div>
      ) : (
        <ResizablePanelGroup direction="horizontal" className="flex-1 overflow-hidden">
          <ResizablePanel defaultSize={25} minSize={15} maxSize={40}>
            {sidebarContent}
          </ResizablePanel>
          <ResizableHandle withHandle className="bg-border hover:bg-primary/50 transition-colors" />
          <ResizablePanel defaultSize={75}>
            <div className="h-full flex flex-col overflow-hidden">
              {isChapterLoading || isTranslating ? (
                <div className="flex-1 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-4 animate-pulse">
                    <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    <span className="text-muted-foreground font-mono text-sm uppercase tracking-wider">
                      {isTranslating ? "Translating..." : "Loading Chapter..."}
                    </span>
                  </div>
                </div>
              ) : (
                <Reader 
                  sentences={displayedSentences} 
                  current={currentSentenceIndex}
                  wordTimestamps={wordTimestamps}
                  currentTime={currentTime}
                  isPlaying={isPlaying}
                  htmlContent={chapterData?.html}
                />
              )}
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      )}
    </div>

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
      
      bookId={bookId}
      chapterHref={currentChapterHref}
      sentences={displayedSentences}
      chapterTitle={metadata?.title || "chapter"}
    />
    </>
  );
}

