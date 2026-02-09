import logging
from pathlib import Path
from typing import Annotated, List, TypedDict, Any, Dict

# LangChain & LangGraph Imports
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

# Internal Module Imports
from core.system_state import SystemStateManager
from core.tools_manager import ToolsManager
# --- NO MORE AcademicSearcher IMPORT HERE ---

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [BRAIN] - %(levelname)s - %(message)s')
logger = logging.getLogger("AcademicBrain")

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    retrieved_context: List[Dict[str, Any]]
    visual_insights: List[str]
    needs_visual_enhancement: bool
    current_asset_id: str

class AcademicBrain:
    def __init__(self, model_name="deepseek-chat"):
        # 1. Specialized Logic Logging (File)
        self.log_file = Path("logs/reasoning_logic.log")
        self.log_file.parent.mkdir(exist_ok=True)
        self.logic_logger = logging.getLogger("ReasoningLogic")
        self.logic_logger.setLevel(logging.INFO)
        
        if self.logic_logger.hasHandlers():
            self.logic_logger.handlers.clear()
            
        fh = logging.FileHandler(self.log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s - [LOGIC-TRACE] - %(message)s'))
        self.logic_logger.addHandler(fh)

        # 2. Resource & Tool Managers
        self.state_manager = SystemStateManager()
        self.tools = ToolsManager()
        # self.searcher = AcademicSearcher() # <-- Removed
        
        # 3. LLM Setup
        self.llm = ChatOpenAI(model=model_name, temperature=0.1)
        
        # 4. Graph Construction
        self.workflow = self._create_workflow()
        self.app = self.workflow.compile(checkpointer=MemorySaver())
        
        self.logic_logger.info("SYSTEM_INIT: Academic Brain online. Searcher set to Subprocess mode.")

    # --- Nodes Definition ---

    def node_sentinel_guard(self, state: AgentState):
        if not self.state_manager.is_query_allowed():
            self.logic_logger.warning("GUARD_BLOCKED: Query attempted during Ingestion task.")
            return {"messages": [AIMessage(content="SYSTEM_STATUS_LOCKED")]}
        return {"messages": []}

    def node_academic_retriever(self, state: AgentState):
        """Step 2: Vector Retrieval via Subprocess."""
        asset_id = state.get("current_asset_id")
        last_user_msg = state["messages"][-1].content
        
        self.logic_logger.info(f"RETRIEVAL_SUBPROCESS: Querying for '{last_user_msg[:50]}...'")
        
        # --- CHANGED: Using ToolsManager to dispatch to a separate process ---
        # Note: You need to add 'call_searcher' method to your ToolsManager
        search_results = self.tools.call_searcher(
            query=last_user_msg, 
            asset_id=asset_id, 
            top_k=5
        )
        
        if not search_results or isinstance(search_results, dict) and search_results.get("status") == "error":
            self.logic_logger.warning(f"RETRIEVAL_FAILED: {search_results}")
            return {"retrieved_context": []}

        # Log Top Hits
        for i, res in enumerate(search_results[:3]):
            self.logic_logger.info(f"RETRIEVAL_HIT[{i}]: Modality={res['modality']}, Score={res['score']:.4f}")
        
        return {"retrieved_context": search_results}

    # ... node_vlm_decision and other nodes remain largely same ...

    def node_final_synthesis(self, state: AgentState):
        # Same as before, using retrieved_context from state
        # ... (Refer to previous code)
        pass

    def _create_workflow(self):
        # Same Graph Construction
        # ...
        pass

    def ask(self, query: str, asset_id: str = None, thread_id: str = "user_01"):
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [HumanMessage(content=query)], "current_asset_id": asset_id}
        self.logic_logger.info(f"--- NEW_SESSION_START: Thread={thread_id} ---")
        return self.app.invoke(inputs, config)