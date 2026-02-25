"use client";
import { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, Upload, Activity, MessageSquare, FileText, PanelLeftClose, PanelLeftOpen, Send, PlayCircle } from 'lucide-react';
import type { Asset, AssetStatus } from '../lib/types';
import AssetCard from '../components/AssetCard';
import { API_ENDPOINTS, BASE_URL } from '../lib/api-config';

export default function ScaffoldingPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<{url: string, type: 'pdf' | 'video'} | null>(null);
  const [isOutlineOpen, setIsOutlineOpen] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [activeOutline, setActiveOutline] = useState<any[]>([]);
  const [isLoadingOutline, setIsLoadingOutline] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const pdfRef = useRef<HTMLIFrameElement>(null);

  // --- 逻辑：获取预览路径 ---
  const fetchPreviewPath = async (assetId: string) => {
    try {
      const res = await fetch(`${API_ENDPOINTS.PREVIEW}?asset_id=${encodeURIComponent(assetId)}`);
      const data = await res.json();
      if (data.raw_path) {
        // 拼接完整地址：http://localhost:8001/raw/video/xxx.mp4
        setPreviewData({
          url: `${BASE_URL}${data.raw_path}`,
          type: data.type
        });
      }
    } catch (e) {
      console.error("Fetch preview failed", e);
    }
  };

    const formatAnchor = (anchor: number, type: 'pdf' | 'video') => {
    if (type === 'video') {
      const totalSeconds = Math.floor(anchor);
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }
    return `P.${Math.floor(anchor)}`; 
  };

  const fetchAssetStructure = async (assetId: string) => {
    setIsLoadingOutline(true);
    try {
      const res = await fetch(`${API_ENDPOINTS.STRUCTURE}?asset_id=${encodeURIComponent(assetId)}`);
      const result = await res.json();
      if (result.status === "success" && result.data?.outline?.outline) {
        setActiveOutline(result.data.outline.outline); 
      } else {
        setActiveOutline([]);
      }
    } catch (e) { console.error("Fetch structure failed", e); setActiveOutline([]); }
    finally { setIsLoadingOutline(false); }
  };

  // --- 逻辑：处理资产选择 ---
  const handleSelectAsset = async (id: string) => {
    const asset = assets.find(a => a.id === id);
    setSelectedAssetId(id);
    
    if (asset?.status === 'Ready') {
      fetchAssetStructure(id); 
      fetchPreviewPath(id);    
    } else {
      // 如果资产还没准备好，清空之前的预览和结构
      setPreviewData(null);
      setActiveOutline([]);
    }
  };

  // --- 逻辑：跳转功能 ---
  const handleJump = (anchor: number) => {
  if (!previewData) return;

  if (previewData.type === 'video' && videoRef.current) {
    videoRef.current.currentTime = anchor;
    videoRef.current.play().catch(e => console.warn("Auto-play blocked", e));
  } 
  else if (previewData.type === 'pdf' && pdfRef.current) {
    const pageNum = Math.max(1, Math.floor(anchor));
    
    // 方案：构造一个带随机参数的 URL 强制浏览器刷新 iframe 内容
    const url = new URL(previewData.url);
    
    // 1. 添加一个随机参数，让浏览器认为资源已改变
    url.searchParams.set('t', Date.now().toString());
    
    // 2. 构造符合 PDF 标准的 Hash 参数
    // #page=N 是标准，#toolbar=1&navpanes=0 是为了保持 UI 一致
    const targetSrc = `${url.toString()}#page=${pageNum}&toolbar=1&navpanes=0&view=FitH`;
    
    // 3. 执行跳转
    console.log("PDF Jumping to:", targetSrc);
    pdfRef.current.src = targetSrc;

    // 4. 可选：视觉反馈（闪烁效果）
    pdfRef.current.style.opacity = '0.7';
    setTimeout(() => {
        if(pdfRef.current) pdfRef.current.style.opacity = '1';
    }, 150);
  }
};

  // --- 强化归一化函数 ---
  const normalizeAsset = useCallback((backendData: any): Asset => {
    const status = (backendData.status || 'Raw') as AssetStatus;
    return {
      id: backendData.asset_id,
      name: backendData.asset_id, 
      type: backendData.asset_type || (backendData.asset_id.endsWith('.pdf') ? 'pdf' : 'video'),
      status: status,
      created_at: backendData.created_at || new Date().toISOString(),
      asset_processed_path: backendData.asset_processed_path,
      progress: status === 'Ready' ? 100 : 0,
      outline: [] 
    };
  }, []);

  // --- 全量/增量刷新函数 ---
  const refreshAssetStatuses = async () => {
    try {
      const res = await fetch(API_ENDPOINTS.STATUS); 
      const result = await res.json();
      if (result.status === "success") {
        const rawDataMap = result.data;
        const updatedAssets = Object.values(rawDataMap).map(normalizeAsset);
        setAssets(updatedAssets);
        const hasActiveTasks = updatedAssets.some(a => !['Ready', 'Raw', 'Failed'].includes(a.status));
        if (!hasActiveTasks && isSyncing) setIsSyncing(false);
        if (hasActiveTasks && !isSyncing) setIsSyncing(true);
      }
    } catch (e) { console.error("Poll failed", e); }
  };

  // --- 初始加载 ---
  useEffect(() => { refreshAssetStatuses(); }, []);

  // --- 轮询控制 ---
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    if (isSyncing) {
      refreshAssetStatuses();
      timer = setInterval(refreshAssetStatuses, 2000);
    }
    return () => { if (timer) clearInterval(timer); };
  }, [isSyncing]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(API_ENDPOINTS.UPLOAD, { method: 'POST', body: formData });
      if (res.ok) await refreshAssetStatuses();
    } catch (err) { console.error("Upload failed", err); }
    finally { setIsUploading(false); e.target.value = ""; }
  };

  const handleGlobalSync = async () => {
    if (isSyncing) return;
    try {
      const res = await fetch(API_ENDPOINTS.SYNC, { method: 'POST' });
      const data = await res.json();
      if (data.status === "success" || data.message?.includes("started")) setIsSyncing(true);
    } catch (err) { console.error("Sync trigger failed", err); }
  };



  return (
    <div className="flex flex-col h-screen w-full bg-dracula-bg text-dracula-fg overflow-hidden font-sans">
      <header className="h-14 border-b border-dracula-comment/30 shrink-0 flex items-center px-6 justify-between bg-dracula-bg/80 backdrop-blur-md z-20">
        <div className="flex items-center gap-4 group cursor-default">
          <div className="flex flex-col items-center border-r border-dracula-comment/30 pr-4">
            <Activity size={20} className="text-dracula-cyan mb-0.5" />
          </div>
          <div className="flex flex-col leading-tight">
            <div className="flex items-center gap-2">
              <span className="text-xs font-black tracking-[0.2em] text-dracula-fg uppercase italic">ACADEMIC AGENT</span>
              <span className="text-[10px] text-dracula-purple font-mono border border-dracula-purple/30 px-1 rounded">v2.0</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-0.5 w-3 bg-dracula-cyan" />
          <h1 className="text-sm font-bold text-dracula-purple tracking-tighter uppercase">
            <span className="text-dracula-pink mr-3">Multimodal</span> 
            <span className="text-dracula-purple">Engine</span>
          </h1>
          <span className="h-0.5 w-3 bg-dracula-cyan" />
        </div>
      </header>

      <main className="flex flex-1 overflow-hidden min-h-0">
        <div className="flex-1 flex border-r border-dracula-comment relative overflow-hidden">
          {/* 修改点：左侧大纲栏取消横向溢出 */}
          <aside className={`${isOutlineOpen ? 'w-80' : 'w-0'} transition-all duration-300 border-r border-dracula-comment bg-dracula-bg overflow-x-hidden overflow-y-auto custom-scrollbar`}>
            <div className="p-4 w-80 wrap-break-word"> {/* 增加强制换行 */}
              <h3 className="text-xs font-bold text-dracula-comment uppercase mb-4 tracking-widest flex items-center gap-2 border-b border-dracula-comment/30 pb-2">
                <Activity size={14} className="text-dracula-cyan" /> 结构化大纲
              </h3>

              {isLoadingOutline ? (
                <div className="flex flex-col items-center justify-center py-10 gap-3 text-dracula-comment font-mono text-[10px]">
                  <RefreshCw size={24} className="animate-spin text-dracula-purple" />
                  <span className="animate-pulse">ANALYZING_STRUCTURE...</span>
                </div>
              ) : selectedAssetId && activeOutline.length > 0 ? (
                <div className="space-y-6">
                  {activeOutline.map((item, idx) => {
                    const assetType = assets.find(a => a.id === selectedAssetId)?.type || 'pdf';
                    return (
                      <div key={idx} className="group">
                        <div className="flex justify-between items-start gap-2 mb-1">
                          {/* 标题部分增加样式防止溢出 */}
                          <div 
                            className="text-sm font-bold text-dracula-cyan cursor-pointer hover:text-dracula-pink transition-colors leading-tight flex-1"
                            onClick={() => handleJump(item.anchor)}
                          >
                            {idx + 1}. {item.heading}
                          </div>
                          <span className="text-[9px] font-mono text-dracula-comment mt-1 opacity-50 shrink-0">
                            {formatAnchor(item.anchor, assetType)}
                          </span>
                        </div>
                        <p className="text-[10px] text-dracula-comment leading-relaxed mb-3 italic line-clamp-2 hover:line-clamp-none transition-all">
                          {item.summary}
                        </p>
                        <div className="pl-3 border-l border-dracula-comment/50 space-y-2">
                          {item.sub_points?.map((sub: any, sIdx: number) => (
                            <div 
                              key={sIdx} 
                              className="hover:bg-dracula-current/50 p-2 rounded-sm transition-all cursor-pointer group/sub border border-transparent hover:border-dracula-comment/30"
                              onClick={() => handleJump(sub.anchor)}
                            >
                              <div className="text-[11px] text-dracula-fg flex justify-between items-start gap-2">
                                <span className="leading-snug group-hover/sub:text-dracula-purple transition-colors flex-1">
                                  • {sub.heading}
                                </span>
                                <span className="text-dracula-purple font-mono text-[9px] shrink-0 bg-dracula-purple/10 px-1.5 py-0.5 rounded tabular-nums">
                                  {formatAnchor(sub.anchor, assetType)}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-20 border border-dashed border-dracula-comment/20 rounded-lg text-center">
                  <FileText size={32} className="text-dracula-comment/20 mb-2" />
                  <p className="text-[10px] text-dracula-comment font-mono italic px-4 whitespace-normal">
                    {selectedAssetId ? "STRUCTURE_PENDING_OR_EMPTY" : "PLEASE_SELECT_ASSET_TO_VIEW_ANALYSIS"}
                  </p>
                </div>
              )}
            </div>
          </aside>

          <section className="flex-1 bg-dracula-current relative flex items-center justify-center overflow-hidden">
            <button 
              onClick={() => setIsOutlineOpen(!isOutlineOpen)} 
              className="absolute left-4 top-4 z-30 p-2 bg-dracula-bg/80 backdrop-blur border border-dracula-comment rounded hover:bg-dracula-comment transition-colors"
            >
              {isOutlineOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </button>

            {previewData ? (
              <div className="w-full h-full flex items-center justify-center bg-black/40">
                {previewData.type === 'video' ? (
                  <video 
                    ref={videoRef}
                    src={previewData.url}
                    controls
                    className="max-w-full max-h-full shadow-2xl"
                    playsInline
                  />
                ) : (
                  <div className="w-full h-full bg-[#525659] relative flex items-center justify-center">
                    {/* 增加 key 属性，当切换资产时彻底销毁旧 iframe */}
                    <iframe 
                      key={selectedAssetId} 
                      ref={pdfRef}
                      // view=FitH 自动横向撑满，navpanes=0 隐藏左侧缩略图栏
                      src={`${previewData.url}#toolbar=1&navpanes=0&view=FitH`}
                      className="w-full h-full border-none bg-white"
                      title="PDF Preview"
                    />
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center gap-4 opacity-20 group">
                <FileText size={64} className="group-hover:scale-110 transition-transform duration-500" />
                <span className="font-mono text-sm tracking-widest uppercase">
                  {selectedAssetId ? "Loading_Stream..." : "Viewer_Standby"}
                </span>
              </div>
            )}
          </section>
        </div>

        <aside className="w-112.5 flex flex-col bg-dracula-bg shrink-0 border-l border-dracula-comment">
          <div className="p-4 border-b border-dracula-comment text-dracula-pink flex items-center gap-2 font-bold">
            <MessageSquare size={18} /> 智能研讨
          </div>
          <div className="flex-1 p-4 font-mono text-xs text-dracula-comment leading-relaxed">
            [SYSTEM]: 会话就绪。
            <br/>[STATUS]: 向量数据库连接正常。
          </div>
          <div className="p-4 border-t border-dracula-comment">
            <div className="relative">
              <input type="text" placeholder="Terminal > _" className="w-full bg-dracula-current p-3 rounded border border-dracula-comment focus:border-dracula-purple transition-all outline-none font-mono text-sm" />
              <Send size={18} className="absolute right-3 top-3 text-dracula-comment" />
            </div>
          </div>
        </aside>
      </main>

      <footer className="h-80 border-t border-dracula-comment bg-dracula-bg p-4 z-10 shrink-0 flex flex-col">
        <div className="flex items-center justify-between mb-4 shrink-0">
          <div className="flex items-center gap-4">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <Upload size={16} className="text-dracula-green" /> 资产管理
            </h3>
            {assets.some(a => a.status === 'Raw') && !isSyncing && (
              <button 
                onClick={handleGlobalSync} 
                disabled={isSyncing} 
                className="flex items-center gap-2 px-4 py-1.5 bg-dracula-purple/20 border border-dracula-purple text-dracula-purple rounded-md text-[10px] font-bold hover:bg-dracula-purple hover:text-dracula-bg transition-all active:scale-95 disabled:opacity-50"
              >
                <RefreshCw size={12} className={isSyncing ? 'animate-spin' : ''} />
                {isSyncing ? "INGESTING_PHASE..." : "INVOKE_PIPELINE"}
              </button>
            )}
          </div>
          <label className={`px-4 py-1.5 rounded-md text-xs font-bold cursor-pointer transition-all shadow-lg ${isUploading ? 'bg-dracula-comment cursor-not-allowed' : 'bg-dracula-green text-dracula-bg hover:bg-dracula-yellow hover:-translate-y-0.5'}`}>
            {isUploading ? "STREAMING..." : "UPLOAD_ASSET"}
            <input 
              type="file" 
              className="hidden" 
              onChange={handleUpload} 
              disabled={isUploading || isSyncing} // 此处已包含 isSyncing
              accept=".pdf,.mp4,.mkv,.mov,.avi" 
            />
          </label>
        </div>

        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
          <div className="grid grid-cols-2 gap-4">
            {assets.map(asset => (
              <AssetCard 
                key={asset.id}
                asset={asset} 
                onSelect={handleSelectAsset}
                isSelected={selectedAssetId === asset.id}
              />
            ))}
          </div>
          <div className="h-2" />
        </div>
      </footer>
    </div>
  );
}