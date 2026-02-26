// components/PdfViewer.tsx
"use client";
import { useEffect, useRef, useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';

interface PdfViewerProps {
  url: string;
  page: number;
  bbox?: string;
  onPageChange?: (newPage: number) => void;
}

export default function PdfViewer({ url, page, bbox, onPageChange }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(false);

  // 1. 核心改进：使用 ResizeObserver 监听容器尺寸变化
  // 这解决了“点击按钮变大窗口”时，高亮框坐标不跟随的问题
  useEffect(() => {
    if (!containerRef.current) return;

    const updateScale = () => {
      if (containerRef.current) {
        const PDF_BASE_WIDTH = 595.28; // 标准 A4 磅数
        const currentWidth = containerRef.current.clientWidth;
        if (currentWidth > 0) {
          setScale(currentWidth / PDF_BASE_WIDTH);
        }
      }
    };

    const resizeObserver = new ResizeObserver(() => {
      // 使用 requestAnimationFrame 确保在浏览器重绘前更新，防止抖动
      requestAnimationFrame(updateScale);
    });

    resizeObserver.observe(containerRef.current);
    updateScale(); // 初始化执行

    return () => resizeObserver.disconnect();
  }, [url]); 

  // 页码切换视觉效果
  useEffect(() => {
    setIsLoading(true);
    const timer = setTimeout(() => setIsLoading(false), 400);
    return () => clearTimeout(timer);
  }, [page, url]);

  const highlightStyle = useMemo(() => {
    if (!bbox || scale === 0) return null;
    try {
      const coords = typeof bbox === 'string' ? JSON.parse(bbox) : bbox;
      const [xmin, ymin, xmax, ymax] = coords;
      return {
        position: 'absolute' as const,
        left: `${xmin * scale}px`,
        top: `${ymin * scale}px`,
        width: `${(xmax - xmin) * scale}px`,
        height: `${(ymax - ymin) * scale}px`,
        backgroundColor: 'rgba(255, 121, 198, 0.25)', 
        border: '1px solid #ff79c6',
        boxShadow: '0 0 15px rgba(255, 121, 198, 0.3)',
        borderRadius: '2px',
        pointerEvents: 'none' as const,
        zIndex: 20,
        // 增加 transition，当窗口尺寸改变（按钮触发变大）时，高亮框会平滑滑向新位置
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)', 
      };
    } catch (e) { return null; }
  }, [bbox, scale]);

  return (
    <div className="relative w-full h-full flex flex-col bg-dracula-bg/50 overflow-hidden">
      
      {/* 悬浮页码条 */}
      <div className="absolute top-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-1 bg-dracula-bg/80 backdrop-blur-md border border-dracula-comment/30 p-1.5 rounded-full shadow-2xl">
        <button 
          onClick={() => onPageChange?.(Math.max(1, page - 1))}
          className="p-1.5 hover:bg-dracula-purple/20 hover:text-dracula-purple rounded-full text-dracula-comment transition-all active:scale-90"
        >
          <ChevronLeft size={18} />
        </button>
        
        <div className="flex items-center px-3 border-x border-dracula-comment/20">
          <span className="text-[11px] font-mono font-black text-dracula-pink tracking-widest">
            PAGE <span className="text-dracula-fg ml-1">{page.toString().padStart(2, '0')}</span>
          </span>
        </div>

        <button 
          onClick={() => onPageChange?.(page + 1)}
          className="p-1.5 hover:bg-dracula-purple/20 hover:text-dracula-purple rounded-full text-dracula-comment transition-all active:scale-90"
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {/* 预览区域：外层容器负责滚动，内层容器负责比例锁定 */}
      <div className="flex-1 w-full overflow-y-auto overflow-x-hidden flex justify-center p-8 pt-24 custom-scrollbar">
        
        <div 
          ref={containerRef} 
          className={`
            relative w-full max-w-5xl aspect-[1/1.5] h-fit bg-white shadow-[0_20px_60px_rgba(0,0,0,0.4)] 
            overflow-hidden transition-all duration-500 ease-in-out
            ${isLoading ? 'scale-[0.99] opacity-70 blur-[1px]' : 'scale-100 opacity-100 blur-0'}
          `}
        >
          {/* 高亮层 */}
          {highlightStyle && (
            <div 
              style={highlightStyle} 
              className="animate-in fade-in zoom-in-95 duration-500" 
            />
          )}

          {/* 加载状态 */}
          {isLoading && (
            <div className="absolute inset-0 z-30 flex items-center justify-center bg-white/20 backdrop-blur-[1px]">
              <Loader2 className="text-dracula-purple animate-spin" size={32} />
            </div>
          )}
          
          <div className="w-full h-full relative pointer-events-none">
            {/* 强行撑开并隐藏 iframe 的原生滚动条 */}
            <iframe
              key={`${url}-${page}`}
              src={`${url}#page=${page}&view=FitH&toolbar=0&navpanes=0&scrollbar=0`}
              className="absolute border-none"
              style={{ 
                width: 'calc(100% + 30px)', 
                height: '100%',
                left: '0',
                top: '0',
                marginRight: '-30px'
              }}
              title="PDF Preview"
            />
          </div>
        </div>
      </div>

      {/* 底部修饰 */}
      <div className="h-1 w-full bg-gradient-to-r from-transparent via-dracula-purple/30 to-transparent opacity-50" />
    </div>
  );
}