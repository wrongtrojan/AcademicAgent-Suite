import logging
from typing import Dict, Any

# Import core components from the root directory
from core.tools_manager import ToolsManager
from core.ingestion_stream import IngestionStream
from core.reasoning_stream import ReasoningStream
from core.system_state import SystemStateManager
from core.asset_scanner import AssetScanner

# Standardized logging for Orchestrator
logger = logging.getLogger("WebOrchestrator")

class AgentLogicOrchestrator:
    """
    The central gateway for the Web layer to interact with the Core logic.
    Ensures singletons of heavy core services and provides clean async interfaces.
    """
    def __init__(self):
        logger.info("Initializing AgentLogicOrchestrator... (Building the Brain Bridge)")
        
        # 1. Initialize State Manager (Singleton)
        self.state_manager = SystemStateManager()
        
        # 2. Initialize Hardware/Subprocess Gateway
        self.tools = ToolsManager()
        
        # 3. Initialize Domain Streams
        self.ingestor = IngestionStream(self.tools)
        self.reasoner = ReasoningStream(self.tools)
        self.scanner = AssetScanner()
        
        logger.info("AgentLogicOrchestrator: All core services are online.")

    def request_ingestion_lock(self, task_id: str) -> bool:
        return self.state_manager.acquire_ingestion_lock(task_id)

    async def trigger_sync(self):
        logger.info("Orchestrator: Starting background ingestion task...")
        try:
            await self.ingestor.run_global_sync()
        except Exception as e:
            logger.error(f"Orchestrator: Ingestion task failed: {str(e)}")
        finally:
            self.state_manager.reset_progress()
            self.state_manager.release_lock()
            logger.info("Orchestrator: Ingestion lock released and state reset.")

    def get_system_snapshot(self) -> Dict[str, Any]:
        """
        Retrieves the current state of the system (VRAM locks, progress, etc.)
        """
        return self.state_manager.get_full_state()

    def stream_chat(self, query: str, thread_id: str):
        """
        Gateway for streaming reasoning.
        Returns the asynchronous generator from the ReasoningStream.
        """
        logger.info(f"Orchestrator: Routing streaming request for thread [{thread_id}]")
        # Directly return the generator coroutine
        return self.reasoner.stream_query(query, thread_id)
    
    def get_assets_map(self) -> list:
        """
        Orchestrates asset scanning. 
        In the future, this can be wrapped with caching logic here.
        """
        logger.info("Orchestrator: Requesting global asset scan...")
        return self.scanner.scan_all_assets()
    
# --- Singleton Container for FastAPI Lifespan ---
# This ensures that we only instantiate the Core once per server process.
orchestrator_instance: Dict[str, AgentLogicOrchestrator] = {}

def get_orchestrator() -> AgentLogicOrchestrator:
    """FastAPI Dependency Provider."""
    if "core" not in orchestrator_instance:
        # Fallback if lifespan wasn't triggered, though lifespan is preferred.
        orchestrator_instance["core"] = AgentLogicOrchestrator()
    return orchestrator_instance["core"]

