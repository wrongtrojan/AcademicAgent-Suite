export const BASE_URL = "http://localhost:8001"; 

export const API_ENDPOINTS = {
  // 1. 资产上传与同步
  UPLOAD: `${BASE_URL}/api/v1/upload/file`,
  SYNC: `${BASE_URL}/api/v1/assets/sync`,
  
  // 2. 状态查询 (支持 single_asset?asset_id=xxx)
  STATUS: `${BASE_URL}/api/v1/status/single_asset`,
  
  // 3. 内容获取
  STRUCTURE: `${BASE_URL}/api/v1/assets/structure`,
  PREVIEW: `${BASE_URL}/api/v1/assets/preview`,
  
  // 4. 对话相关
  CHAT_CREATE: `${BASE_URL}/api/v1/chats/create`,
  CHAT_STREAM: `${BASE_URL}/api/v1/chats/stream`,
};