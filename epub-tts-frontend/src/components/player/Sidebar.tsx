import { useState } from "react";
import type { NavItem } from "epubjs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { Book, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const API_BASE = "http://localhost:8000/api";

interface SidebarProps {
  toc: NavItem[];
  currentChapterHref: string;
  onSelectChapter: (href: string) => void;
  coverUrl?: string;
  title?: string;
  bookId?: string;  // 用于下载整本书
  selectedVoice?: string;  // 当前选择的语音
  speed?: number;  // 当前语速
}

export function Sidebar({ 
  toc, currentChapterHref, onSelectChapter, coverUrl, title,
  bookId, selectedVoice = "zh-CN-XiaoxiaoNeural", speed = 1.0
}: SidebarProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  // 下载整本书音频（创建后台任务）
  const handleDownloadBook = async () => {
    if (!bookId) {
      toast.error("无法下载：书籍ID不存在");
      return;
    }

    setIsDownloading(true);

    try {
      const response = await fetch(`${API_BASE}/books/${bookId}/download-audio`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice: selectedVoice,
          rate: speed,
          pitch: 1.0
        })
      });

      if (!response.ok) {
        throw new Error("创建任务失败");
      }

      const data = await response.json();
      
      if (data.resumed) {
        toast.success(
          `恢复下载：${data.bookTitle}`, 
          { description: `从第 ${data.resumeFrom + 1} 章继续，点击「任务」查看进度` }
        );
      } else {
        toast.success(
          `已创建后台任务：${data.bookTitle}`, 
          { description: "点击右上角「任务」按钮查看进度" }
        );
      }
    } catch (error) {
      console.error("Download error:", error);
      toast.error("创建任务失败，请重试");
    } finally {
      setIsDownloading(false);
    }
  };

  // Flatten TOC for simplicity if needed, but recursive is better
  const renderItem = (item: NavItem, depth = 0) => (
    <div key={item.id} className="w-full">
      <button
        onClick={() => onSelectChapter(item.href)}
        className={cn(
          "w-full text-left px-3 py-2 text-sm font-mono transition-colors border-l-2 hover:bg-primary/5 hover:text-primary",
          // Compare clean hrefs (remove anchors)
          currentChapterHref.split('#')[0] === item.href.split('#')[0]
            ? "border-primary text-primary bg-primary/10"
            : "border-transparent text-muted-foreground"
        )}
        style={{ paddingLeft: `${(depth + 1) * 12}px` }}
      >
        <span className="line-clamp-1">{item.label}</span>
      </button>
      {item.subitems?.map(sub => renderItem(sub, depth + 1))}
    </div>
  );

  return (
    <div className="h-full flex flex-col bg-card/50 border-r border-border backdrop-blur-md">
      <div className="p-4 border-b border-border bg-card/80">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-16 bg-muted shrink-0 overflow-hidden border border-border">
            {coverUrl ? (
              <img src={coverUrl} alt="Cover" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-secondary">
                <Book className="w-6 h-6 text-muted-foreground" />
              </div>
            )}
          </div>
          <div className="overflow-hidden">
            <h2 className="font-display font-bold text-sm leading-tight line-clamp-2 uppercase tracking-wide">
              {title || "Unknown Book"}
            </h2>
            <div className="flex items-center gap-1 mt-1">
               <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
               <span className="text-[10px] font-mono text-primary">ONLINE</span>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground font-mono uppercase">
           <span>目录</span>
           <span>{toc.length} 章节</span>
        </div>
        
        {/* 下载整本书按钮 */}
        <Button
          variant="outline"
          size="sm"
          onClick={handleDownloadBook}
          disabled={isDownloading || !bookId}
          className="w-full mt-3 border-primary/30 hover:border-primary hover:bg-primary/10 text-xs"
        >
          {isDownloading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
              生成中...
            </>
          ) : (
            <>
              <Download className="w-3.5 h-3.5 mr-2" />
              下载整本书音频
            </>
          )}
        </Button>
      </div>
      
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="flex flex-col gap-0.5 py-2">
            {toc.map(item => renderItem(item))}
          </div>
        </ScrollArea>
      </div>
      
      <div className="p-2 border-t border-border bg-black/20 text-[10px] font-mono text-center text-muted-foreground">
        SYSTEM READY // V1.0.0
      </div>
    </div>
  );
}
