"use client";
import { useState, useEffect, useCallback, useLayoutEffect, useRef } from 'react';
import { RefreshCw, Upload, Activity, MessageSquare, FileText, PanelLeftClose, PanelLeftOpen, Send, PlayCircle, ListTree, ChevronDown, Plus, Terminal } from 'lucide-react';
import type { Asset, AssetStatus, ChatSession, ChatMessage, ChatStatus } from '../lib/types';
import AssetCard from '../components/AssetCard';
import EvidenceCard from '../components/EvidenceCard';
import MarkdownRenderer from '../components/MarkdownRenderer';
import PdfViewer from '../components/PdfViewer';
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

  // 对话相关状态
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [isChatListOpen, setIsChatListOpen] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [inputText, setInputText] = useState("");
  const [chatStatus, setChatStatus] = useState<ChatStatus>('Idle');
  const [currentPage, setCurrentPage] = useState(1);
  const [currentBbox, setCurrentBbox] = useState<string | undefined>(undefined);
  

  const videoRef = useRef<HTMLVideoElement>(null);
  const chatPollingRef = useRef<NodeJS.Timeout | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  
  const scrollToBottom = () => chatEndRef.current?.scrollIntoView({ behavior: "smooth" });

  // --- 逻辑：获取会话历史 ---
  const fetchInitialChats = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/status/single_chat`);
      const result = await res.json();
      if (result.status === "success") {
        // 后端返回的是 Map { id: details }
        const chatList = Object.values(result.data) as ChatSession[];
        setChats(chatList);
        if (chatList.length > 0 && !activeChatId) {
          setActiveChatId(chatList[0].chat_id);
        }
      }
    } catch (e) { console.error("Fetch chats failed", e); }
  };

  useEffect(() => { fetchInitialChats(); }, []);

  // --- 逻辑：创建新会话 (修正报错 1) ---
  const createNewChat = async () => {
    try {
      const res = await fetch(API_ENDPOINTS.CHAT_CREATE, { method: 'POST' });
      const data = await res.json();
      if (data.chat_id) {
        const newChat: ChatSession = {
          chat_id: data.chat_id,
          chat_name: `New Chat ${data.chat_id.slice(-4)}`,
          status: 'Idle',
          messages: [],
          evidence: [],
          last_active: new Date().toISOString()
        };
        setChats(prev => [newChat, ...prev]);
        setActiveChatId(data.chat_id);
        setIsChatListOpen(false);
      }
    } catch (e) { console.error("Create chat failed", e); }
  };

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
      setCurrentPage(1);
      setCurrentBbox(undefined);
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
    else if (previewData.type === 'pdf') {
      const pageNum = Math.max(1, Math.floor(anchor));
      // 修改点：必须更新状态，PdfViewer 才会响应
      setCurrentPage(pageNum);
      setCurrentBbox(undefined); // 大纲跳转通常不带高亮，清空旧高亮
      console.log("PDF Requesting Page:", pageNum);
    }
  };

  const handleEvidenceJump = async (assetName: string, anchor: number, bbox?: string) => {
    const targetAsset = assets.find(a => a.name === assetName);
    if (!targetAsset) return;

    // --- [修改部位 1: 统一处理资产切换逻辑] ---
    if (selectedAssetId !== targetAsset.id) {
      setSelectedAssetId(targetAsset.id);
      fetchAssetStructure(targetAsset.id); 
      fetchPreviewPath(targetAsset.id);
    }

    // --- [修改部位 2: 分类型执行跳转指令] ---
    if (targetAsset.type === 'video') {
      // 视频跳转：如果当前已经在播放该视频，直接跳时间；如果是切过来的，需要等 Ref 挂载
      if (videoRef.current) {
        videoRef.current.currentTime = anchor;
        videoRef.current.play().catch(e => console.warn("Auto-play blocked", e));
      } else {
        // 这是一个边缘情况：如果切换了资产，video 标签可能还没渲染好
        // 我们可以通过预设一个临时变量或在 useEffect 中监听 previewData 来处理，
        // 但最简单严谨的方法是给一个小延迟或依赖现有 videoRef 的可用性
        setTimeout(() => {
          if (videoRef.current) {
            videoRef.current.currentTime = anchor;
            videoRef.current.play().catch(e => console.warn("Auto-play blocked", e));
          }
        }, 150); // 150ms 足够 React 完成 DOM 节点的初步挂载
      }
    } else {
      // PDF 跳转：保持原有逻辑
      setCurrentPage(Math.max(1, Math.floor(anchor)));
      setCurrentBbox(bbox);
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

  useLayoutEffect(() => {
    if (isAtBottomRef.current && isStreaming) {
      const scrollContainer = chatEndRef.current?.parentElement;
      if (!scrollContainer) return;

      // 第一帧：立即设置滚动高度，减少视觉闪烁
      scrollContainer.scrollTop = scrollContainer.scrollHeight;

      // 第二帧：确保在渲染后再次确认位置
      const frameId = requestAnimationFrame(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "instant" });
      });
      
      return () => cancelAnimationFrame(frameId);
    }
  }, [chats, isStreaming]); // 移除 chatStatus，减少干扰

  useEffect(() => {
    const container = chatEndRef.current?.parentElement;
    if (!container) return;

    const resizeObserver = new ResizeObserver(() => {
      // 只要容器高度变了，且用户之前就在底部，就强行锁死到底部
      if (isAtBottomRef.current) {
        chatEndRef.current?.scrollIntoView({ behavior: "instant" });
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []); // 仅挂载时执行一次

  const handleSendMessage = async () => {
    if (!inputText.trim() || !activeChatId || isStreaming) return;

    const userMsgText = inputText;
    const currentId = activeChatId; // 闭包锁定
    setInputText("");
    setIsStreaming(true);
    
    // A. 插入用户消息占位
    const newUserMsg: ChatMessage = { role: 'user', message: userMsgText, timestamp: new Date().toISOString() };
    setChats(prev => prev.map(c => c.chat_id === currentId ? { ...c, messages: [...c.messages, newUserMsg] } : c));

    isAtBottomRef.current = true;
    requestAnimationFrame(() => {
      chatEndRef.current?.scrollIntoView({ behavior: "instant" });
    });

    // B. 【强硬点】立即开启状态轮询，监听 Searching, Evaluating 等状态
    startChatPolling(currentId);

    let assistantContent = "";
    const eventSource = new EventSource(`${API_ENDPOINTS.CHAT_STREAM}?chat_id=${currentId}&message=${encodeURIComponent(userMsgText)}`);

    eventSource.addEventListener('message', (event) => {
      const data = JSON.parse(event.data);
      if (data.status === 'processing' && data.content) {
        assistantContent += data.content;
        setChats(prev => prev.map(c => {
          if (c.chat_id !== currentId) return c;
          const lastMsg = c.messages[c.messages.length - 1];
          if (lastMsg && lastMsg.timestamp === 'streaming') {
            const newMessages = [...c.messages];
            newMessages[newMessages.length - 1] = { ...lastMsg, message: assistantContent };
            return { ...c, messages: newMessages };
          } else {
            return { ...c, messages: [...c.messages, { role: 'assistant', message: assistantContent, timestamp: 'streaming' }] };
          }
        }));
      }

      if (data.status === 'completed') {
        eventSource.close();
        setIsStreaming(false);
        // 推送结束，最后再同步一次最终状态和证据
        fullSyncChat(currentId);
      }
    });

    eventSource.addEventListener('error', () => {
      eventSource.close();
      setIsStreaming(false);
      setChatStatus('Failed');
      stopChatPolling();
    });
  };

  const startChatPolling = (id: string) => {
    stopChatPolling(); // 先清理
    chatPollingRef.current = setInterval(() => syncSingleChat(id), 1500); // 1.5s 高频轮询
  };

  const stopChatPolling = () => {
    if (chatPollingRef.current) {
      clearInterval(chatPollingRef.current);
      chatPollingRef.current = null;
    }
  };

  const fullSyncChat = async (id: string) => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/status/single_chat?chat_id=${id}`);
      const result = await res.json();
      if (result.status === "success" && result.data) {
        const remoteDetail = result.data[id] || result.data;
        setChats(prev => prev.map(c => 
          c.chat_id === id ? { ...c, ...remoteDetail } : c
        ));
        if (id === activeChatId) setChatStatus(remoteDetail.status || 'Idle');
      }
    } catch (e) { console.error("Full sync failed", e); }
  };

  const syncSingleChat = useCallback( async (id: string) => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/status/single_chat?chat_id=${id}`);
      const result = await res.json();
      
      if (result.status === "success" && result.data) {
        const remoteDetail = result.data[id] || result.data; 
        
        setChats(prev => prev.map(c => {
          if (c.chat_id === id) {
            return {
              ...c,
              status: remoteDetail.status || 'Idle',
              evidence: remoteDetail.evidence || c.evidence,
            };
          }
          return c;
        }));

        setChatStatus(prev => {
          if (id === activeChatId) return remoteDetail.status || 'Idle';
          return prev;
        });

        // 如果后端返回状态已经是 Idle 或 Failed，说明推理结束，停止轮询
        if (['Idle', 'Failed', 'Completed'].includes(remoteDetail.status)) {
          stopChatPolling();
          fullSyncChat(id);
        }
      }
    } catch (e) { console.error("Chat sync error", e); }
  },[activeChatId]);


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
              <h3 className="text-sm font-bold text-dracula-comment uppercase mb-4 tracking-widest flex items-center gap-2 border-b border-dracula-comment/30 pb-2">
                <ListTree size={14} className="text-dracula-cyan" /> 结构化大纲
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
                    <PdfViewer 
                      url={previewData.url} 
                      page={currentPage} 
                      bbox={currentBbox} 
                      // 【修改点 5】绑定页码变更回调
                      onPageChange={(newPage) => {
                        setCurrentPage(newPage);
                        setCurrentBbox(undefined); // 手动翻页时自动清除旧高亮
                      }}
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

        <aside className="w-112.5 flex flex-col bg-dracula-bg shrink-0 border-l border-dracula-comment relative">
          {/* 会话选择器 Header */}
          <div className="p-3 border-b border-dracula-comment flex items-center justify-between bg-dracula-current/20">
            <div className="relative">
              <button 
                onClick={() => setIsChatListOpen(!isChatListOpen)}
                className="flex items-center gap-2 text-xs font-bold text-dracula-pink hover:text-dracula-fg transition-colors"
              >
                <MessageSquare size={14} /> 
                {chats.find(c => c.chat_id === activeChatId)?.chat_name || "选择研讨会话"}
                <ChevronDown size={12} className={`transition-transform ${isChatListOpen ? 'rotate-180' : ''}`} />
              </button>
              
              {/* 下拉菜单 */}
              {isChatListOpen && (
                <div className="absolute top-full left-0 mt-2 w-64 bg-dracula-bg border border-dracula-comment shadow-2xl z-50 rounded-md overflow-hidden">
                  <button 
                    onClick={createNewChat}
                    className="w-full p-3 text-left text-[10px] font-bold text-dracula-green border-b border-dracula-comment hover:bg-dracula-current flex items-center gap-2"
                  >
                    <Plus size={12} /> NEW_CONVERSATION_THREAD
                  </button>
                  <div className="max-h-60 overflow-y-auto custom-scrollbar">
                    {chats.map(chat => (
                      <div 
                        key={chat.chat_id}
                        onClick={() => { setActiveChatId(chat.chat_id); setIsChatListOpen(false); }}
                        className={`p-3 text-[11px] cursor-pointer hover:bg-dracula-current transition-colors border-b border-dracula-comment/30 ${activeChatId === chat.chat_id ? 'bg-dracula-current text-dracula-cyan' : 'text-dracula-fg'}`}
                      >
                        {chat.chat_name}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 对话内容区 */}
          <div 
            className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar relative"
            // [ADD] 滚动监听：判断用户是否在底部（预留 50px 缓冲区）
            onScroll={(e) => {
              const target = e.currentTarget;
              const offset = 50; // 容差值
              const atBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + offset;
              isAtBottomRef.current = atBottom;
            }}
          >
            {/* 浮动推理状态条：仅在非 Idle 状态时显示 */}
            {chatStatus !== 'Idle' && chatStatus !== 'Failed' && (
              <div className="sticky top-0 z-10 flex justify-center mb-4">
                <div className="flex items-center gap-3 px-4 py-2 bg-dracula-purple/10 border border-dracula-purple/30 backdrop-blur-md rounded-full shadow-lg animate-in fade-in zoom-in duration-300">
                  <div className="relative flex items-center justify-center">
                    <div className="w-2 h-2 rounded-full bg-dracula-purple animate-ping absolute" />
                    <div className="w-2 h-2 rounded-full bg-dracula-purple relative" />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-black text-dracula-purple tracking-widest uppercase italic">
                      AI_THINKING_FLOW: {chatStatus}
                    </span>
                    {/* 进度步进条指示 */}
                    <div className="flex gap-1 mt-1">
                      {['Preparing', 'Researching', 'Evaluating', 'Strengthening', 'Finalizing'].map((s) => (
                        <div 
                          key={s} 
                          className={`h-1 w-6 rounded-full transition-all duration-500 ${
                            chatStatus === s ? 'bg-dracula-purple w-10' : 'bg-dracula-comment/20'
                          }`} 
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div className="flex flex-col gap-4 w-full"> 
              {chats.find(c => c.chat_id === activeChatId)?.messages.map((msg, i) => {
               // [FIX] 只有该会话的最后一条消息展示证据
               const isLastMessage = i === (chats.find(c => c.chat_id === activeChatId)?.messages.length || 0) - 1;
               const currentEvidence = chats.find(c => c.chat_id === activeChatId)?.evidence || [];

               return (
                <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div className={`max-w-[90%] p-3 rounded-lg text-sm leading-relaxed ${
                    msg.role === 'user' 
                    ? 'bg-dracula-purple/20 border border-dracula-purple/30 text-dracula-fg' 
                    : 'bg-dracula-current/50 border border-dracula-comment/30 text-dracula-fg'
                  }`}>
                    <MarkdownRenderer content={msg.message} />
                  </div>
                  {/* [FIX] 仅在 AI 且非流式传输时展示证据卡片 */}
                  {msg.role === 'assistant' && msg.timestamp !== 'streaming' && isLastMessage && currentEvidence.length > 0 && (
                    <div className="mt-3 w-full space-y-2 animate-in fade-in slide-in-from-top-2">
                      <div className="text-[10px] font-bold text-dracula-comment uppercase tracking-widest flex items-center gap-2 px-1">
                        <ListTree size={10} /> Grounded Evidence
                      </div>
                      {currentEvidence.slice(0, 2).map((ev, ei) => (
                        <EvidenceCard key={ei} evidence={ev} onJump={handleEvidenceJump} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            </div>
            <div 
              id="chat-end-ref" 
              ref={chatEndRef} 
              className="h-4 w-full shrink-0" 
            />
          </div>

          {/* 输入框 */}
          <div className="p-4 border-t border-dracula-comment bg-dracula-bg">
            <div className="relative flex items-center gap-2 bg-dracula-current rounded-lg border border-dracula-comment p-2 focus-within:border-dracula-purple transition-all">
              <Terminal size={14} className="text-dracula-comment shrink-0" />
              <input 
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                disabled={isStreaming || !activeChatId}
                placeholder={activeChatId ? "输入指令进行学术探讨..." : "请先选择或创建会话"}
                className="w-full bg-transparent outline-none font-mono text-xs text-dracula-fg disabled:opacity-50"
              />
              <button 
                onClick={handleSendMessage}
                disabled={isStreaming || !inputText.trim()}
                className="p-1 hover:text-dracula-pink transition-colors disabled:opacity-0"
              >
                <Send size={18} />
              </button>
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
          {assets.length > 0 ? (
            // 如果有资产，显示网格列表
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
        ) : (
          // 如果没有资产，显示虚线占位框
          <div className="h-full min-h-30 border-2 border-dashed border-dracula-comment/30 rounded-xl flex flex-col items-center justify-center group hover:border-dracula-green/50 transition-colors">
            <div className="p-3 rounded-full bg-dracula-comment/10 mb-2 group-hover:bg-dracula-green/10 transition-colors">
              <Upload size={24} className="text-dracula-comment/40 group-hover:text-dracula-green/60" />
            </div>
            <p className="text-[10px] font-mono text-dracula-comment uppercase tracking-widest">
              No assets deployed. Waiting for upload...
            </p>
          </div>
        )}
        <div className="h-2" />
          </div>
        </footer>
    </div>
  );
}