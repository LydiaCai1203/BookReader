import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { UploadZone } from "@/components/player/UploadZone";
import { useUploadBook } from "@/hooks/use-book";
import { Button } from "@/components/ui/button";
import { Loader2, Book, Trash2, BrainCircuit, Github } from "lucide-react";
import { toast } from "sonner";
import { API_BASE, API_URL } from "@/config";
import { TasksPanel } from "@/components/player/TasksPanel";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface BookInfo {
  id: string;
  title: string;
  author?: string;
  coverUrl?: string;
  lastOpened?: string;
}

export default function Home() {
  const [, navigate] = useLocation();
  const [books, setBooks] = useState<BookInfo[]>([]);
  const [isLoadingBooks, setIsLoadingBooks] = useState(true);
  const [deleteBookId, setDeleteBookId] = useState<string | null>(null);
  
  const uploadMutation = useUploadBook();

  // 加载书架
  useEffect(() => {
    loadBooks();
  }, []);

  const loadBooks = async () => {
    setIsLoadingBooks(true);
    try {
      const res = await fetch(`${API_URL}/books`);
      if (!res.ok) throw new Error("Failed to load books");
      const data = await res.json();
      setBooks(data.map((book: any) => ({
        id: book.id,
        title: book.title || "Unknown",
        author: book.author,
        coverUrl: book.coverUrl ? `${API_BASE}${book.coverUrl}` : undefined,
        lastOpened: book.lastOpened,
      })));
    } catch (error) {
      console.error("Failed to load books:", error);
    } finally {
      setIsLoadingBooks(false);
    }
  };

  const handleFileSelect = (file: File) => {
    toast.promise(uploadMutation.mutateAsync(file), {
      loading: '正在上传并解析书籍...',
      success: (data) => {
        // 上传成功后直接跳转到阅读页
        navigate(`/book/${data.bookId}`);
        return "书籍已就绪";
      },
      error: "加载失败"
    });
  };

  const handleBookClick = (bookId: string) => {
    navigate(`/book/${bookId}`);
  };

  const handleDeleteBook = async () => {
    if (!deleteBookId) return;
    
    try {
      const res = await fetch(`${API_URL}/books/${deleteBookId}`, {
        method: "DELETE"
      });
      if (!res.ok) throw new Error("Failed to delete book");
      
      toast.success("书籍已删除");
      setBooks(books.filter(b => b.id !== deleteBookId));
    } catch (error) {
      console.error("Failed to delete book:", error);
      toast.error("删除失败");
    } finally {
      setDeleteBookId(null);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/80 backdrop-blur-md py-3 px-4 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BrainCircuit className="w-7 h-7 text-primary" />
            <span className="font-display text-xl font-bold tracking-tight">
              BookReader
            </span>
          </div>
          
          <div className="flex items-center gap-2">
            <TasksPanel />
            <Button
              variant="ghost"
              size="icon"
              asChild
            >
              <a href="https://github.com" target="_blank" rel="noopener noreferrer">
                <Github className="w-5 h-5" />
              </a>
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Upload Section */}
        <section className="mb-12">
          <h2 className="text-lg font-semibold mb-4 text-foreground">上传新书</h2>
          <UploadZone 
            onFileSelect={handleFileSelect} 
            isLoading={uploadMutation.isPending} 
          />
        </section>

        {/* Bookshelf Section */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">我的书架</h2>
            <span className="text-sm text-muted-foreground">{books.length} 本书</span>
          </div>

          {isLoadingBooks ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
            </div>
          ) : books.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Book className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>书架空空如也</p>
              <p className="text-sm mt-1">上传一本 EPUB 开始阅读吧</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {books.map((book) => (
                <div
                  key={book.id}
                  className="group relative bg-card rounded-lg border border-border overflow-hidden hover:border-primary/50 hover:shadow-lg transition-all cursor-pointer"
                  onClick={() => handleBookClick(book.id)}
                >
                  {/* Cover */}
                  <div className="aspect-[2/3] bg-muted overflow-hidden">
                    {book.coverUrl ? (
                      <img 
                        src={book.coverUrl} 
                        alt={book.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-primary/20 to-primary/5">
                        <Book className="w-12 h-12 text-primary/50" />
                      </div>
                    )}
                  </div>
                  
                  {/* Info */}
                  <div className="p-3">
                    <h3 className="font-medium text-sm line-clamp-2 leading-tight">
                      {book.title}
                    </h3>
                    {book.author && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                        {book.author}
                      </p>
                    )}
                  </div>

                  {/* Delete button */}
                  <button
                    className="absolute top-2 right-2 p-1.5 rounded-full bg-background/80 backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive hover:text-destructive-foreground"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteBookId(book.id);
                    }}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteBookId} onOpenChange={() => setDeleteBookId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要从书架中删除这本书吗？此操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteBook} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
