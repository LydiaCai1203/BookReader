import { useState, useCallback, useEffect } from "react";
import { Upload, BookOpen, FileMusic, PlayCircle, Trash2, Book, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

const API_BASE = "http://localhost:8000/api";

interface BookItem {
  id: string;
  title: string;
  creator: string;
  coverUrl?: string;
  addedAt: string;
  lastOpenedAt: string;
}

interface UploadZoneProps {
  onFileSelect: (file: File) => void;
  onDemoSelect: () => void;
  onBookSelect?: (bookId: string) => void;  // 选择已有书籍
}

export function UploadZone({ onFileSelect, onDemoSelect, onBookSelect }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [books, setBooks] = useState<BookItem[]>([]);
  const [isLoadingBooks, setIsLoadingBooks] = useState(true);

  // 获取书架列表
  useEffect(() => {
    const fetchBooks = async () => {
      try {
        const response = await fetch(`${API_BASE}/books`);
        if (response.ok) {
          const data = await response.json();
          setBooks(data);
        }
      } catch (error) {
        console.error("Failed to fetch books:", error);
      } finally {
        setIsLoadingBooks(false);
      }
    };
    fetchBooks();
  }, []);

  // 删除书籍
  const handleDeleteBook = async (bookId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定要删除这本书吗？")) return;
    
    try {
      const response = await fetch(`${API_BASE}/books/${bookId}`, {
        method: "DELETE"
      });
      if (response.ok) {
        setBooks(books.filter(b => b.id !== bookId));
      }
    } catch (error) {
      console.error("Failed to delete book:", error);
    }
  };

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragging(true);
    } else if (e.type === "dragleave") {
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.name.endsWith(".epub")) {
        onFileSelect(file);
      } else {
        alert("Please upload an EPUB file");
      }
    }
  }, [onFileSelect]);

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileSelect(e.target.files[0]);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] w-full max-w-2xl mx-auto p-6">
      <div className="mb-8 text-center space-y-4">
        <h1 className="text-6xl font-display font-bold tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-primary via-primary/80 to-primary/50 text-glow">
          CYBER READER
        </h1>
        <p className="text-muted-foreground text-lg font-mono">
          EPUB TO AUDIO // NEURAL LINK ESTABLISHED
        </p>
      </div>

      <div
        className={cn(
          "relative w-full aspect-video rounded-none border-2 border-dashed transition-all duration-300 flex flex-col items-center justify-center gap-4 bg-card/50 backdrop-blur-sm group cursor-pointer overflow-hidden mb-6",
          isDragging
            ? "border-primary bg-primary/10 scale-[1.02] shadow-[0_0_30px_rgba(204,255,0,0.2)]"
            : "border-muted-foreground/30 hover:border-primary/50 hover:bg-card/80"
        )}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => document.getElementById("file-upload")?.click()}
      >
        {/* Decor elements */}
        <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-primary opacity-50 group-hover:opacity-100 transition-opacity" />
        <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-primary opacity-50 group-hover:opacity-100 transition-opacity" />
        <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-primary opacity-50 group-hover:opacity-100 transition-opacity" />
        <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-primary opacity-50 group-hover:opacity-100 transition-opacity" />
        
        {/* Animated grid background */}
        <div className="absolute inset-0 bg-grid-pattern opacity-[0.03] pointer-events-none" />

        <div className="relative z-10 flex flex-col items-center gap-4 group-hover:-translate-y-1 transition-transform duration-300">
          <div className="p-4 rounded-full bg-primary/10 border border-primary/20 group-hover:bg-primary/20 transition-colors">
            <Upload className="w-8 h-8 text-primary" />
          </div>
          <div className="text-center">
            <h3 className="text-xl font-bold font-display text-foreground group-hover:text-primary transition-colors">
              UPLOAD EPUB
            </h3>
            <p className="text-sm text-muted-foreground font-mono mt-1">
              DRAG & DROP OR CLICK TO BROWSE
            </p>
          </div>
        </div>

        <input
          id="file-upload"
          type="file"
          accept=".epub"
          className="hidden"
          onChange={handleInput}
        />
      </div>

      {/* 书架 - 已有书籍列表 */}
      {books.length > 0 && (
        <div className="w-full mt-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-display font-bold tracking-wide text-foreground">
              我的书架
            </h2>
            <span className="text-xs font-mono text-muted-foreground">
              {books.length} 本书
            </span>
          </div>
          
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {books.map((book) => (
              <div
                key={book.id}
                onClick={() => onBookSelect?.(book.id)}
                className="group relative bg-card/50 border border-border hover:border-primary/50 rounded-sm overflow-hidden cursor-pointer transition-all hover:shadow-[0_0_20px_rgba(204,255,0,0.1)] hover:-translate-y-1"
              >
                {/* 封面 */}
                <div className="aspect-[3/4] bg-secondary overflow-hidden">
                  {book.coverUrl ? (
                    <img 
                      src={book.coverUrl} 
                      alt={book.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-primary/20 to-primary/5">
                      <Book className="w-12 h-12 text-primary/40" />
                    </div>
                  )}
                </div>
                
                {/* 书名和作者 */}
                <div className="p-3">
                  <h3 className="font-medium text-sm line-clamp-2 group-hover:text-primary transition-colors">
                    {book.title}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                    {book.creator || "未知作者"}
                  </p>
                </div>
                
                {/* 删除按钮 */}
                <button
                  onClick={(e) => handleDeleteBook(book.id, e)}
                  className="absolute top-2 right-2 p-1.5 bg-black/60 hover:bg-destructive rounded-sm opacity-0 group-hover:opacity-100 transition-opacity"
                  title="删除"
                >
                  <Trash2 className="w-3.5 h-3.5 text-white" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 加载状态 */}
      {isLoadingBooks && (
        <div className="flex items-center gap-2 text-muted-foreground mt-8">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm font-mono">加载书架中...</span>
        </div>
      )}

      {/* 空状态提示 */}
      {!isLoadingBooks && books.length === 0 && (
        <div className="text-center text-muted-foreground mt-8">
          <Book className="w-12 h-12 mx-auto mb-2 opacity-30" />
          <p className="text-sm font-mono">书架空空如也，上传你的第一本书吧</p>
        </div>
      )}
    </div>
  );
}

function FeatureItem({ icon: Icon, label }: { icon: any; label: string }) {
  return (
    <div className="flex flex-col items-center gap-2 p-3 border border-border/50 bg-card/30 backdrop-blur hover:border-primary/50 transition-colors">
      <Icon className="w-5 h-5 text-primary/80" />
      <span className="text-xs font-mono text-muted-foreground">{label}</span>
    </div>
  );
}
