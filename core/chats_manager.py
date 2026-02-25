import logging
import os
import json
import httpx
import uuid
from pathlib import Path
import asyncio
from enum import Enum
from typing import List, Dict, Optional, Any, Union
from datetime import datetime
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# 内部组件
from core.services_manager import ServicesManager
from core.prompts_manager import PromptManager

# --- 枚举定义 ---
class ChatStatus(Enum):
    PREPARING = "Preparing"     # 结构化需求
    RESEARCHING = "Researching" # 搜索中
    EVALUATING = "Evaluating"   # 质量评估
    STRENGTHENING = "Strengthening" # 沙盒/视觉增强
    FINALIZING = "Finalizing"   # 组织答案
    IDLE = "Idle"               # 会话挂起/完成
    FAILED = "Failed"           # 发生错误

class GlobalChatStatus(Enum):
    QUERYING = "Querying"       # 至少有一个会话正在活跃
    WAITING = "Waiting"         # 无活跃会话

# --- 数据模型 ---
class ChatMessage(BaseModel):
    role: str
    message: str
    timestamp: str = datetime.now().isoformat()

class ChatSession:
    def __init__(self, chat_id: str, chat_name: str):
        self.chat_id = chat_id
        self.chat_name = chat_name
        self.status = ChatStatus.IDLE
        self.messages: List[ChatMessage] = []
        self.evidence: List[Dict] = []
        self.retry_count = 0
        self.start_time = datetime.now().isoformat()
        self.last_update = datetime.now().isoformat()

    # --- 新增：从字典恢复会话对象 ---
    @classmethod
    def from_dict(cls, data: Dict):
        session = cls(data['chat_id'], data['chat_name'])
        session.status = ChatStatus(data['status'])
        session.retry_count = data.get('retry_count', 0)
        session.start_time = data.get('uptime', datetime.now().isoformat())
        session.last_update = data.get('last_active', datetime.now().isoformat())
        # 恢复消息列表
        if 'messages' in data: # 假设你在 to_dict 里补齐了 messages
             session.messages = [ChatMessage(**m) for m in data['messages']]
        # 恢复证据
        session.evidence = data.get('evidence', [])
        return session

    def update_status(self, new_status: ChatStatus):
        self.status = new_status
        self.last_update = datetime.now().isoformat()

    def to_dict(self):
        # 补全了 messages 和 evidence 的导出，确保持久化完整
        return {
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "status": self.status.value,
            "messages": [m.model_dump() for m in self.messages], 
            "evidence": self.evidence,
            "messages_count": len(self.messages),
            "evidence_count": len(self.evidence),
            "retry_count": self.retry_count,
            "uptime": self.start_time,
            "last_active": self.last_update
        }

# --- 核心管理器 ---
class ChatsManager:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ChatsManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"): return
        self.services = ServicesManager()
        self.prompt_manager = PromptManager()
        
        # 活跃会话存储
        self.active_chats: Dict[str, ChatSession] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        
        # LLM 配置
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        
        # 路径配置
        self.storage_dir = Path("./storage/chats")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # --- 关键新增：启动时加载本地数据 ---
        self._load_local_sessions()
        
        self.logger = logging.getLogger("ChatsManager")
        logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s')
        self._initialized = True
        
    def _log(self, chat_id: str, level: str, msg: str):
        extra = f"[{chat_id}]"
        if level == "info": self.logger.info(f"{extra} - {msg}")
        elif level == "error": self.logger.error(f"{extra} - {msg}")
        elif level == "warn": self.logger.warning(f"{extra} - {msg}")

    # --- 核心方法 ---

    async def _direct_llm_call(self, prompt_or_messages: Union[str, List[Dict]], json_mode: bool = True, stream: bool = False) -> Any:
        """支持流式的 LLM 调用"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = prompt_or_messages
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "stream": stream # 新增流式开关
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        # 增加超时设置
        timeout = httpx.Timeout(180.0, connect=10.0)
        client = httpx.AsyncClient(timeout=timeout)
        
        if not stream:
            async with client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                content = response.json()['choices'][0]['message']['content']
                if json_mode:
                    clean_content = content.replace("```json", "").replace("```", "").strip()
                    return json.loads(clean_content)
                return content
        else:
            # 流式返回模式 (注意：流式通常不建议配合 json_mode 使用)
            async def gen():
                full_content = []
                try:
                    async with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as r:
                        r.raise_for_status()
                        async for line in r.aiter_lines():
                            if not line or line == "data: [DONE]": continue
                            if line.startswith("data: "):
                                data = json.loads(line[6:])
                                delta = data['choices'][0]['delta'].get('content', '')
                                if delta:
                                    full_content.append(delta)
                                    yield delta
                finally:
                    await client.aclose()
            return gen()
    
    def _load_local_sessions(self):
        """扫描 storage 目录，恢复所有历史会话到内存"""
        count = 0
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    session = ChatSession.from_dict(data)
                    # 重启后状态统一设为 IDLE，防止卡在 Researching
                    if session.status != ChatStatus.FAILED:
                        session.status = ChatStatus.IDLE
                    self.active_chats[session.chat_id] = session
                    count += 1
            except Exception as e:
                print(f"Error loading session {file_path}: {e}")
        if count > 0:
            print(f"成功从本地加载了 {count} 个历史会话")

    def save_session(self, chat_id: str):
        session = self.active_chats.get(chat_id)
        if not session: return
        storage_path = self.storage_dir / f"{chat_id}.json"
        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    # --- API 视察接口 ---

    def get_overall_status(self) -> dict:
        is_querying = any(c.status != ChatStatus.IDLE for c in self.active_chats.values())
        return {
            "chats_number": len(self.active_chats),
            "chats_status": GlobalChatStatus.QUERYING.value if is_querying else GlobalChatStatus.WAITING.value,
            "timestamp": datetime.now().isoformat()
        }

    def get_all_chats(self) -> Dict[str, dict]:
        return {cid: session.to_dict() for cid, session in self.active_chats.items()}
    
    def get_chat_details(self, chat_id: str) -> Optional[dict]:
        session = self.active_chats.get(chat_id)
        return session.to_dict() if session else None

    # --- 核心推理流 (直连版) ---

    async def create_empty_chat(self) -> str:
        """[修改点] 无需参数创建 chat_id"""
        chat_id = f"CH-{uuid.uuid4().hex[:8].upper()}"
        # 初始名字设为 New Chat，后续根据第一条消息自动重命名
        self.active_chats[chat_id] = ChatSession(chat_id, "New Academic Chat")
        self.save_session(chat_id)
        return chat_id

    async def execute_reasoning_flow(self, chat_id: str, user_message: str):
        if chat_id not in self.active_chats:
            raise ValueError("Session not found")
        
        session = self.active_chats[chat_id]
        
        # 1. 追加新消息到历史
        history_context = [{"role": m.role, "content": m.message} for m in session.messages[-6:]]
        
        # 记录当前用户消息
        session.messages.append(ChatMessage(role="user", message=user_message))
        if len(session.messages) <= 1:
            session.chat_name = f"Chat-{user_message[:12]}"

        # 用于搜索阶段的 Query（结合最近几轮对话防止指代不明）
        search_context_str = "\n".join([f"{m['role']}: {m['content']}" for m in history_context] + [f"user: {user_message}"])
        
        try:
            # 1. Preparing: 结构化需求 (直连)
            session.update_status(ChatStatus.PREPARING)
            self.save_session(chat_id) # 状态变更即持久化
            
            prep_prompt = self.prompt_manager.render("query_refiner", query=search_context_str)
            # search_needs 已经是符合 {search_params: ..., preferences: ...} 结构的字典
            search_needs = await self._direct_llm_call(prep_prompt)

            # 2 & 3. Researching & Evaluating: 搜索循环 (逻辑决策直连)
            session.update_status(ChatStatus.RESEARCHING)
            session.retry_count = 0
            while session.retry_count < 2:
                self._log(chat_id, "info", f"Phase 2: Searching (Attempt {session.retry_count+1})...")
                
                search_response = await self.services.start_academic_search(search_needs)
                
                # 解析返回结果 (strengthened_search 返回 {"status": "success", "results": [...]})
                if search_response.get("status") == "success":
                    search_results = search_response.get("results", [])
                else:
                    self._log(chat_id, "error", f"Search failed: {search_response.get('message')}")
                
                # 确保结果是列表才进行 extend
                if isinstance(search_results, list):
                    session.evidence.extend(search_results)
                
                # Evaluating: 判断信息充足性 (直连)
                session.update_status(ChatStatus.EVALUATING)
                eval_prompt = self.prompt_manager.render(
                    "evidence_evaluator", 
                    query=search_context_str, 
                    docs=session.evidence,
                    retry_count=session.retry_count # 传入重试次数辅助 LLM 决策
                )
                eval_report = await self._direct_llm_call(eval_prompt)

                if eval_report.get("action") == "proceed":
                    self._log(chat_id, "info", "Evidence confirmed by LLM.")
                    break
                
                session.retry_count += 1
                session.update_status(ChatStatus.RESEARCHING)

            # 4. Strengthening: 意图检查与专家调用 (决策直连)
            session.update_status(ChatStatus.STRENGTHENING)
            self._log(chat_id, "info", "Phase 4: Strengthening via Experts...")
            intent_prompt = self.prompt_manager.render("intent_check", query=search_context_str, docs=session.evidence)
            intent = await self._direct_llm_call(intent_prompt)
            print(f"Intent Check Result: {intent}") # 调试输出
            vlm_res, sandbox_res = "N/A", "N/A"
            if intent.get("need_vision") and session.evidence:
                # 寻找第一个视频证据来获取帧路径
                video_doc = next((d for d in session.evidence if d.get("metadata", {}).get("modality") == "video"), None)
                if video_doc:
                    meta = video_doc.get("metadata", {})
                    asset_name = meta.get("asset_name")
                    ts = meta.get("timestamp", 0)
                    
                    # 构造对齐存储结构的路径
                    frame_path = f"storage/processed/video/{asset_name}/frames/time_{ts}.jpg"
                    
                    # 获取策略指令
                    strategy_key = intent.get("vision_strategy", "scene_description")
                    # 注意：这里假设 chats_manager 能访问到 strategies 配置，或者通过 prompt_manager 处理
                    vlm_instruction = f"Strategy: {strategy_key}. Context: {search_context_str}" 

                    vlm_params = {
                        "image": frame_path,
                        "prompt": vlm_instruction
                    }
                    self._log(chat_id, "info", f"Calling Vision Expert for frame at {ts}s")
                    vlm_output = await self.services.call_visual_expert(params=vlm_params)
                    vlm_res = vlm_output.get("response", "Vision parse failed.")

            if intent.get("need_sandbox"):
                self._log(chat_id, "info", "Calling Sandbox for logic verification...")
                # 1. 提取公式与准备代码 (直连)
                combined_evidence = " ".join([str(d.get("content", "")) for d in session.evidence])
                sb_prep_prompt = self.prompt_manager.render("sandbox_prep", context=combined_evidence)
                sb_instructions = await self._direct_llm_call(sb_prep_prompt)
                
                # 2. 调用沙箱专家 (传递准备好的指令字典)
                if sb_instructions.get("expression") != "empty":
                    sandbox_output = await self.services.call_sandbox_expert(params=sb_instructions)
                    sandbox_res = f"Verified Result: {sandbox_output.get('result', 'Calculation failed')}"
                else:
                    sandbox_res = "No complex formulas to verify."

            # 5. Finalizing: 最终合成 (生成直连)
            session.update_status(ChatStatus.FINALIZING)
            self._log(chat_id, "info", "Phase 5: Synthesizing final answer...")
            
            # 渲染最终提示词，注意 docs 此时已包含所有搜索到的 evidence
            final_prompt = self.prompt_manager.render(
                "synthesizer", 
                query=user_message, 
                docs=session.evidence, 
                vlm_feedback=vlm_res, 
                math_res=sandbox_res
            )
            full_messages = history_context + [{"role": "user", "content": final_prompt}]
            response_gen = await self._direct_llm_call(full_messages, json_mode=False, stream=True)
            full_answer = ""
            async for token in response_gen:
                full_answer += token
                yield token # 向外部 API 层吐出流式 Token
            
            session.messages.append(ChatMessage(role="assistant", message=str(full_answer)))
            session.update_status(ChatStatus.IDLE)

        except Exception as e:
            session.update_status(ChatStatus.FAILED)
            self._log(chat_id, "error", f"Flow Error: {str(e)}")
            yield f"Error encountered: {str(e)}"
        finally:
            self.save_session(chat_id)