// --- 资产状态枚举 (严格对应后端 AssetStatus) ---
export type AssetStatus = 
  | 'Uploading'    // 点击上传中
  | 'Raw'          // 已落盘，待解析
  | 'recognizing'  // 正在识别 (PDF OCR/视频语音)
  | 'Cliping'      // 正在分段
  | 'Structuring'  // 正在生成结构化大纲
  | 'Ingesting'    // 正在注入数据库
  | 'Ready'        // 完成
  | 'Failed';      // 失败

// --- 对话推理状态枚举 (严格对应后端 ChatStatus) ---
export type ChatStatus = 
  | 'Preparing' 
  | 'Researching' 
  | 'Evaluating' 
  | 'Strengthening' 
  | 'Finalizing' 
  | 'Idle' 
  | 'Failed';

// --- 基础数据结构 ---

export interface OutlineSubPoint {
  heading: string;
  anchor: number; // 视频是秒数，PDF是页码
  summary: string;
}

export interface OutlineItem {
  heading: string;
  anchor: number;
  summary: string;
  sub_points: OutlineSubPoint[];
}

export interface Asset {
  id: string;
  name: string;
  type: 'pdf' | 'video';
  status: AssetStatus;
  created_at: string;
  asset_processed_path?: string;
  // 以下为前端 UI 辅助字段
  progress?: number; 
  outline?: OutlineItem[]; 
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  message: string;
  timestamp: string;
}

export interface Evidence {
  content: string;
  score: number;
  metadata: {
    asset_name: string;
    modality: 'pdf' | 'video';
    page_label?: number;      // PDF 页码
    timestamp?: number;        // 视频秒数
    bbox?: string;             // 重点：后端返回的 "[ymin, xmin, ymax, xmax]" 字符串
  };
}

export interface ChatSession {
  chat_id: string;
  chat_name: string;
  status: ChatStatus;
  messages: ChatMessage[];
  evidence: Evidence[]; // 存储后端返回的搜索证据
  last_active: string;
}

// --- API 响应类型定义 ---

export interface SingleAssetResponse {
  status: 'success' | 'error';
  data: {
    asset_id: string;
    asset_type: 'pdf' | 'video';
    status: AssetStatus;
    asset_raw_path: string;
    asset_processed_path: string;
    created_at: string;
    retry_count: number;
  } | Record<string, any>; // 模式A返回Map，模式B返回对象
}

export interface StructureResponse {
  status: 'success' | 'processing';
  data?: {
    title: string;
    outline: OutlineItem[];
  };
  current_step?: string;
  message?: string;
}