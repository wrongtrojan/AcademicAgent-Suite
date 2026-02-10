import logging
import asyncio
from typing import  List, Dict, Any, TypedDict
from pathlib import Path
from langgraph.graph import StateGraph, END
import re
import json
# External state and tools management
from core.tools_manager import ToolsManager
from core.system_state import SystemStateManager, SystemStatus

# Standard logging configuration
logger = logging.getLogger("ReasoningStream")

class AgentState(TypedDict):
    """
    Main state object for LangGraph, capturing the context across nodes.
    Aligned with PROPOSAL.md for academic reasoning and pruning.
    """
    query: str                       # Original user query
    retrieved_docs: List[Dict]       # Documents from searcher with metadata
    verification_results: List[Any]  # Results from Sandbox execution
    vlm_feedback: str               # Feedback from Visual Expert (if needed)
    reasoning_chain: List[str]       # Internal CoT logs (to be pruned later)
    final_answer: str                # Polished response for the user
    citations: List[str]             # List of [Timestamp/Page] anchors
    status: str                      # Current workflow status

class ReasoningStream:
    def __init__(self, tools_manager: ToolsManager):
        """
        Initialize the reasoning engine with tool gateway and VRAM guard.
        """
        self.tools = tools_manager
        self.state_manager = SystemStateManager()
        self.project_root = Path(__file__).resolve().parent.parent

    async def _check_resource_lock(self) -> bool:
        """
        Interrogates the SystemStateManager to ensure VRAM is available.
        Prevents collision with Track A (Ingestion).
        """
        if not self.state_manager.is_query_allowed():
            logger.error("VRAM Guard: Query denied. Ingestion task in progress.")
            return False
        return True

    async def execute_query(self, query: str, asset_id: str = None):
        """
        The main async entry point for Track B reasoning flow.
        """
        # Step 1: Resource Admission Control
        if not await self._check_resource_lock():
            return {
                "status": "error", 
                "message": "System is busy processing assets. Please wait."
            }

        # Initial State setup
        initial_state: AgentState = {
            "query": query,
            "retrieved_docs": [],
            "verification_results": [],
            "vlm_feedback": "",
            "reasoning_chain": [f"User initiated query: {query}"],
            "final_answer": "",
            "citations": [],
            "status": "started"
        }

        logger.info(f"🧠 [Reasoning-Core] Workflow started for query: {query[:50]}...")
        
        # Note: The LangGraph execution logic will be implemented in Phase 3.
        # For now, this serves as the foundational interface.
        return initial_state
    # --- Node Implementation ---

    async def research_node(self, state: AgentState) -> Dict:
        """
        Retrieval Node: Fetches structured evidence and performs smart citation anchoring.
       
        """
        query = state["query"]
        logger.info(f"🔍 [Node: Research] Fetching evidence for: {query[:30]}...")

        search_params = {"query": query, "top_k": 5}
        raw_res = await asyncio.to_thread(self.tools.call_searcher, search_params)
        
        if isinstance(raw_res, list):
            new_docs = raw_res
            # A. Improved Citation Logic: Use a set for auto-deduplication during collection
            citation_set = set()
            for doc in new_docs:
                meta=doc.get("metadata", {})
                modality = meta.get("modality")
                if modality == "video" and meta.get:
                    val = meta.get("timestamp")
                    ts = int(val)
                    citation_set.add(f"[Video @ {ts//60:02d}:{ts%60:02d}]") 
                elif modality == "pdf" and meta.get:
                    val = meta.get("page_label") 
                    citation_set.add(f"[PDF Page {int(val)}]")
            
            sorted_citations = sorted(list(citation_set))
            
            # Sort citations to ensure academic consistency (e.g., Page 1 before Page 10)
            sorted_citations = sorted(list(citation_set))
            
            return {
                "retrieved_docs": new_docs,
                "citations": sorted_citations,
                "reasoning_chain": state["reasoning_chain"] + [f"Retrieved {len(new_docs)} docs with {len(sorted_citations)} unique anchors."],
                "status": "researched"
            }
        return {"status": "error", "reasoning_chain": state["reasoning_chain"] + ["Search failed."]}

    async def logic_node(self, state: AgentState) -> Dict:
        """
        Verification Node: Dynamically extracts and validates formulas.
       
        """
        # B. Dynamic Expression Extraction
        # Simulate LLM extraction by scanning retrieved content for LaTeX-like patterns
        combined_content = " ".join([d["content"] for d in state["retrieved_docs"]])
        
        # Regex to find formulas between $...$ or in common math notation
        # For testing, if no formula found, we fallback to a query-based trigger
        formulas = re.findall(r"\$(.{2,})\$", combined_content) # 至少抓取2个字符
        if formulas:
            # 过滤掉只有等号或标点的噪声
            valid_formulas = [f for f in formulas if any(c.isalnum() for c in f)]
            if valid_formulas:
                target_expr = valid_formulas[0]
            logger.info(f"🔢 [Node: Logic] Extracted formula: {target_expr}. Invoking Sandbox...")
            
            sandbox_params = {
                "expression": target_expr, 
                "mode": "solve",
                "symbol": "x"
            }
            
            verification = await asyncio.to_thread(self.tools.call_sandbox, sandbox_params)
            
            return {
                "verification_results": [verification],
                "reasoning_chain": state["reasoning_chain"] + [f"Verified formula '${target_expr}$' via Sandbox."],
                "status": "verified"
            }
        
        logger.info("🔢 [Node: Logic] No formulas found in context. Skipping verification.")
        return {"reasoning_chain": state["reasoning_chain"] + ["No formulas detected in retrieved chunks."]}

    # --- Routing Logic ---

    def should_continue(self, state: AgentState) -> str:
        """
        Determines the next path in the graph.
       
        """
        if state.get("status") == "error":
            return "end"
        if not state["retrieved_docs"]:
            return "research"
        if state["status"] == "researched":
            return "verify"
        return "synthesize"

    async def synthesize_node(self, state: AgentState) -> Dict:
        """
        Synthesis Node: Finalizes the answer with CoT pruning and citations.
       
        """
        logger.info("✍️ [Node: Synthesis] Finalizing academic response...")
        
        # 1. Gather all verification signals
        is_verified = all(v.get("status") == "success" for v in state["verification_results"]) if state["verification_results"] else None
        
        # 2. Format Context for LLM (Simulated)
        # In a real setup, we pass the retrieved_docs and verification_results to an LLM here.
        # Here we construct the response based on our citation pool.
        
        verification_msg = ""
        if is_verified is True:
            verification_msg = "\n(Verification: This calculation has been validated by the Scientific Sandbox.)"
        elif is_verified is False:
            verification_msg = "\n(Note: Sandbox verification detected potential inconsistencies in the logic.)"

        # 3. Citation Formatting
        citation_text = " ".join(state["citations"])
        
        # Pruning Logic: We only provide the verified conclusion and source anchors
        final_text = (
            f"Based on the analyzed materials, here is the answer to: '{state['query']}'\n\n"
            f"[Conclusion]: ... (Verified logic applied) ...\n"
            f"{verification_msg}\n\n"
            f"Sources: {citation_text}"
        )

        return {
            "final_answer": final_text,
            "status": "completed",
            "reasoning_chain": state["reasoning_chain"] + ["Synthesis complete. Pruned intermediate CoT."]
        }

    def _build_workflow(self):
        """
        Assembles the LangGraph state machine.
        """
        workflow = StateGraph(AgentState)

        # Define Nodes
        workflow.add_node("research", self.research_node)
        workflow.add_node("verify", self.logic_node)
        workflow.add_node("synthesize", self.synthesize_node)

        # Define Edges and Conditional Logic
        workflow.set_entry_point("research")
        
        # Simple linear flow for the baseline; can be branched via should_continue
        workflow.add_edge("research", "verify")
        workflow.add_edge("verify", "synthesize")
        workflow.add_edge("synthesize", END)

        return workflow.compile()

    async def execute_query(self, query: str, asset_id: str = None):
        """
        The main async entry point: Checks VRAM -> Runs Graph -> Returns Result.
       
        """
        # Step 1: Resource Guard
        if not await self._check_resource_lock():
            return {"status": "error", "message": "VRAM Locked by Ingestion."}

        # Step 2: Transition System State to QUERYING
        self.state_manager._current_status = SystemStatus.QUERYING
        
        try:
            # Step 3: Run the Compiled Graph
            app = self._build_workflow()
            
            # Initializing state
            inputs = {
                "query": query,
                "retrieved_docs": [],
                "verification_results": [],
                "vlm_feedback": "",
                "reasoning_chain": [f"Init query: {query}"],
                "final_answer": "",
                "citations": [],
                "status": "started"
            }
            
            # Streaming execution (can use .invoke for non-streaming)
            final_state = await app.ainvoke(inputs)
            
            logger.info(f"✨ [Reasoning-Core] Task complete for query: {query[:30]}")
            return final_state

        finally:
            # Always return to IDLE to release VRAM
            self.state_manager.release_lock()