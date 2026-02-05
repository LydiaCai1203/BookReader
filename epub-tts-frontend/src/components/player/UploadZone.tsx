import { useState, useCallback } from "react";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";

interface UploadZoneProps {
  onFileSelect: (file: File) => void;
  onDemoSelect?: () => void;
}

export function UploadZone({ onFileSelect }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);

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
        alert("请上传 EPUB 格式的文件");
      }
    }
  }, [onFileSelect]);

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileSelect(e.target.files[0]);
    }
  };

  return (
    <div
      className={cn(
        "relative w-full aspect-[3/1] rounded-lg border-2 border-dashed transition-all duration-300 flex flex-col items-center justify-center gap-3 bg-card/50 backdrop-blur-sm group cursor-pointer overflow-hidden",
        isDragging
          ? "border-primary bg-primary/10 scale-[1.01] shadow-[0_0_30px_rgba(204,255,0,0.2)]"
          : "border-muted-foreground/30 hover:border-primary/50 hover:bg-card/80"
      )}
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={() => document.getElementById("file-upload")?.click()}
    >
      {/* Corner decorations */}
      <div className="absolute top-0 left-0 w-3 h-3 border-t-2 border-l-2 border-primary/50 group-hover:border-primary transition-colors" />
      <div className="absolute top-0 right-0 w-3 h-3 border-t-2 border-r-2 border-primary/50 group-hover:border-primary transition-colors" />
      <div className="absolute bottom-0 left-0 w-3 h-3 border-b-2 border-l-2 border-primary/50 group-hover:border-primary transition-colors" />
      <div className="absolute bottom-0 right-0 w-3 h-3 border-b-2 border-r-2 border-primary/50 group-hover:border-primary transition-colors" />

      <div className="relative z-10 flex flex-col items-center gap-2 group-hover:-translate-y-0.5 transition-transform duration-300">
        <div className="p-3 rounded-full bg-primary/10 border border-primary/20 group-hover:bg-primary/20 transition-colors">
          <Upload className="w-6 h-6 text-primary" />
        </div>
        <div className="text-center">
          <h3 className="text-base font-semibold text-foreground group-hover:text-primary transition-colors">
            上传 EPUB 文件
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            拖拽文件到这里，或点击选择
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
  );
}
