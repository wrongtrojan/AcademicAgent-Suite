// EvidenceCard.tsx
import { FileText, PlayCircle } from 'lucide-react';
import { Evidence } from '../lib/types';

interface EvidenceCardProps {
  evidence: Evidence;
  onJump: (assetName: string, anchor: number, bbox?: string) => void;
}

export default function EvidenceCard({ evidence, onJump }: EvidenceCardProps) {
  const { metadata, content } = evidence;
  const isVideo = metadata.modality === 'video';
  
  // 原始数值用于跳转逻辑
  const anchor = isVideo ? (metadata.timestamp || 0) : (metadata.page_label || 1);

  // 格式化函数：确保视频显示为 MM:SS，PDF 显示为 P.XX
  const formatDisplayAnchor = (val: number) => {
    if (isVideo) {
      const totalSeconds = Math.floor(val);
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }
    return `P.${Math.floor(val)}`;
  };

  return (
    <div 
      onClick={() => onJump(metadata.asset_name, anchor, metadata.bbox)}
      className="group flex flex-col gap-2 p-2 bg-dracula-current/30 border border-dracula-comment/20 rounded-md hover:border-dracula-pink/50 transition-all cursor-pointer mb-2"
    >
      <div className="flex items-center justify-between text-[10px]">
        <div className="flex items-center gap-1.5 text-dracula-cyan truncate">
          {isVideo ? <PlayCircle size={12} /> : <FileText size={12} />}
          <span className="truncate max-w-[150px] font-mono">{metadata.asset_name}</span>
        </div>
        {/* 这里使用格式化后的字符串进行渲染 */}
        <span className="text-dracula-purple font-mono bg-dracula-purple/10 px-1.5 py-0.5 rounded">
          {formatDisplayAnchor(anchor)}
        </span>
      </div>
      
      {/* 预览文字（如果有内容） */}
      {content && (
        <p className="text-[10px] text-dracula-comment italic line-clamp-2 leading-tight">
          "{content}"
        </p>
      )}
    </div>
  );
}