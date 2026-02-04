import { useEffect, useRef, useMemo } from "react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { WordTimestamp } from "@/api/types";

interface ReaderProps {
  sentences: string[];
  current: number;
  wordTimestamps?: WordTimestamp[];
  currentTime?: number; // 当前播放时间（毫秒）
  isPlaying?: boolean;
}

export function Reader({ sentences, current, wordTimestamps = [], currentTime = 0, isPlaying = false }: ReaderProps) {
  const activeRef = useRef<HTMLDivElement>(null);
  const activeWordRef = useRef<HTMLSpanElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 计算当前高亮的词索引
  const currentWordIndex = useMemo(() => {
    if (!isPlaying || wordTimestamps.length === 0) return -1;
    
    for (let i = wordTimestamps.length - 1; i >= 0; i--) {
      const word = wordTimestamps[i];
      if (currentTime >= word.offset) {
        return i;
      }
    }
    return -1;
  }, [wordTimestamps, currentTime, isPlaying]);

  // 当章节改变（sentences 变化）时，滚动到顶部
  useEffect(() => {
    if (scrollRef.current) {
      // 找到 ScrollArea 的 viewport 并滚动到顶部
      const viewport = scrollRef.current.querySelector('[data-slot="scroll-area-viewport"]');
      if (viewport) {
        viewport.scrollTop = 0;
      }
    }
  }, [sentences]);

  // 滚动到当前句子
  useEffect(() => {
    if (activeRef.current && current > 0) {
       // 只在不是第一句时滚动到中间，第一句保持在顶部
       activeRef.current.scrollIntoView({
         behavior: "smooth",
         block: "center"
       });
    }
  }, [current]);

  // 滚动到当前高亮词（可选，更平滑的体验）
  useEffect(() => {
    if (activeWordRef.current && isPlaying) {
      activeWordRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
        inline: "center"
      });
    }
  }, [currentWordIndex, isPlaying]);

  if (sentences.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground font-mono uppercase tracking-widest text-sm animate-pulse">
        Waiting for neural data stream...
      </div>
    );
  }

  // 渲染带高亮的文本
  const renderHighlightedText = (text: string, isActive: boolean) => {
    if (!isActive || !isPlaying || wordTimestamps.length === 0) {
      return <span>{text}</span>;
    }

    // 构建高亮渲染
    // 将文本按词分割，然后与 wordTimestamps 匹配
    let result: React.ReactNode[] = [];
    let lastIndex = 0;
    let wordIdx = 0;

    for (const wordTs of wordTimestamps) {
      // 查找这个词在文本中的位置
      const wordStart = text.indexOf(wordTs.text, lastIndex);
      if (wordStart === -1) continue;

      // 添加词之前的文本
      if (wordStart > lastIndex) {
        result.push(
          <span key={`pre-${wordIdx}`} className="transition-colors duration-150">
            {text.slice(lastIndex, wordStart)}
          </span>
        );
      }

      // 判断这个词是否是当前播放的词
      const isCurrentWord = wordIdx === currentWordIndex;
      const isPastWord = wordIdx < currentWordIndex;

      result.push(
        <span
          key={`word-${wordIdx}`}
          ref={isCurrentWord ? activeWordRef : null}
          className={cn(
            "transition-all duration-150 rounded-sm px-0.5 -mx-0.5",
            isCurrentWord 
              ? "bg-primary text-primary-foreground font-semibold shadow-[0_0_12px_rgba(204,255,0,0.6)] scale-105 inline-block" 
              : isPastWord
                ? "text-foreground/90"
                : "text-foreground/60"
          )}
        >
          {wordTs.text}
        </span>
      );

      lastIndex = wordStart + wordTs.text.length;
      wordIdx++;
    }

    // 添加剩余文本
    if (lastIndex < text.length) {
      result.push(
        <span key="rest" className="text-foreground/60">
          {text.slice(lastIndex)}
        </span>
      );
    }

    return result.length > 0 ? result : <span>{text}</span>;
  };

  return (
    <ScrollArea className="h-full w-full px-4 md:px-12 py-8 bg-background relative" ref={scrollRef}>
       <div className="max-w-3xl mx-auto space-y-6 pb-20">
         {sentences.map((text, index) => {
           const isActive = index === current;
           const isPast = index < current;
           
           return (
             <div
               key={index}
               id={`sentence-${index}`}
               ref={isActive ? activeRef : null}
               className={cn(
                 "transition-all duration-500 ease-out p-4 rounded-sm border-l-2",
                 isActive 
                   ? "bg-primary/5 border-primary text-foreground shadow-[0_0_20px_rgba(204,255,0,0.1)] scale-[1.02]" 
                   : isPast 
                     ? "border-transparent text-muted-foreground/40 blur-[0.5px]" 
                     : "border-transparent text-muted-foreground opacity-70"
               )}
             >
               <p className={cn(
                 "leading-relaxed font-serif text-lg md:text-xl",
                 isActive ? "font-medium" : "font-normal"
               )}>
                 {renderHighlightedText(text, isActive)}
               </p>
               {isActive && (
                 <div className="mt-2 flex items-center gap-2">
                    <span className="h-[1px] w-4 bg-primary/50" />
                    <span className="text-[10px] font-mono text-primary uppercase tracking-widest">
                      {isPlaying ? "Reading Now" : "Paused"}
                    </span>
                    {isPlaying && wordTimestamps.length > 0 && (
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {currentWordIndex + 1}/{wordTimestamps.length}
                      </span>
                    )}
                 </div>
               )}
             </div>
           );
         })}
       </div>
    </ScrollArea>
  );
}
