"use client";
import { FileText, PlayCircle, Loader2, Zap, Database, Search, Cpu } from 'lucide-react';
import type { Asset, AssetStatus } from '../lib/types'; 

interface AssetCardProps {
  asset: Asset;
  onSelect: (id: string) => void;
  isSelected: boolean;
}

export default function AssetCard({ asset, onSelect, isSelected }: AssetCardProps) {
  const s = asset.status as AssetStatus;
  
  // 严格状态判定
  const isReady = s === 'Ready';
  const isUploading = s === 'Uploading';
  const isRaw = s === 'Raw';
  const isParsing = ['recognizing', 'Cliping', 'Structuring'].includes(s);
  const isIngesting = s === 'Ingesting';

  // 状态配置映射
  const getStatusConfig = () => {
    if (isUploading) return { color: 'text-dracula-orange', border: 'border-dracula-orange', label: 'UPLOADING', icon: <Loader2 size={10} className="animate-spin" /> };
    if (isRaw) return { color: 'text-dracula-purple', border: 'border-dracula-purple', label: 'RAW_UNSYNCED', icon: <Database size={10} /> };
    if (isParsing) return { color: 'text-dracula-yellow', border: 'border-dracula-yellow', label: s.toUpperCase(), icon: <Cpu size={10} className="animate-pulse" /> };
    if (isIngesting) return { color: 'text-dracula-cyan', border: 'border-dracula-cyan', label: 'INGESTING', icon: <Search size={10} className="animate-bounce" /> };
    return { color: 'text-dracula-green', border: 'border-dracula-green', label: 'STABLE_READY', icon: <Zap size={10} /> };
  };

  const config = getStatusConfig();

  return (
    <div 
      onClick={() => isReady && onSelect(asset.id)}
      className={`
        min-w-80 p-3 border rounded flex flex-col justify-between transition-all duration-500 relative overflow-hidden
        ${isSelected ? 'ring-1 ring-dracula-purple shadow-[0_0_15px_rgba(189,147,249,0.15)] bg-dracula-current border-dracula-purple' : 'border-dracula-comment bg-dracula-bg'}
        ${isReady ? 'cursor-pointer hover:border-dracula-pink' : 'cursor-default'}
      `}
    >
      <div className="flex items-start justify-between z-10">
        <div className="flex items-center gap-3">
          <div className={`${isReady ? (asset.type === 'pdf' ? 'text-dracula-cyan' : 'text-dracula-pink') : 'text-dracula-comment'}`}>
            {asset.type === 'pdf' ? <FileText size={24} /> : <PlayCircle size={24} />}
          </div>
          <div className="overflow-hidden">
            <p className="text-sm font-bold truncate text-dracula-fg">{asset.name}</p>
            <p className="text-[10px] text-dracula-comment font-mono uppercase tracking-tighter">
              {asset.type} • {isReady ? 'Indexed' : 'Phase_Pending'}
            </p>
          </div>
        </div>
        
        <div className={`text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase tracking-widest ${config.border} ${config.color}`}>
          {config.label}
        </div>
      </div>

      <div className="mt-4 min-h-6 z-10">
        {(isParsing || isIngesting || isUploading) ? (
          <div className="space-y-1.5">
            <div className={`flex items-center gap-1.5 text-[10px] font-mono ${config.color}`}>
              {config.icon} {isParsing ? `EXECUTING_${s.toUpperCase()}...` : isUploading ? 'STREAMING_TO_DISK...' : 'WRITING_TO_VECTOR_DB...'}
            </div>
            <div className="w-full bg-dracula-current h-1 rounded-full overflow-hidden relative border border-dracula-comment/20">
               {/* 使用你 globals.css 里的动画 */}
               <div className={`h-full w-1/3 absolute bg-current ${config.color} shadow-[0_0_8px_currentColor] animate-infinite-scroll`} />
            </div>
          </div>
        ) : isRaw ? (
          <div className="flex items-center gap-2 text-[10px] font-mono text-dracula-comment italic">
            <span>{">_"}</span> <span>WAITING_FOR_SYNC_CMD</span>
          </div>
        ) : (
          <div className="text-[10px] font-mono text-dracula-green/90 font-bold flex items-center gap-1.5">
            <Zap size={10} /> ACCESS_GRANTED_STABLE
          </div>
        )}
      </div>

      <div className="flex justify-between mt-3 items-center opacity-80">
        <div className="flex gap-1">
           <div className={`w-1 h-1 rounded-full ${isReady ? 'bg-dracula-green' : 'bg-dracula-comment'}`} />
           <div className={`w-1 h-1 rounded-full ${!isReady && !isRaw ? 'bg-dracula-yellow animate-ping' : 'bg-dracula-comment'}`} />
        </div>
        <span className="text-[9px] text-dracula-comment font-mono uppercase">
          {asset.created_at ? new Date(asset.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '00:00'}
        </span>
      </div>
    </div>
  );
}