import asyncio
import logging
from core.tools_manager import ToolsManager
from core.system_state import SystemStateManager

# Standardized logging in English
logger = logging.getLogger("IngestionStream")

class IngestionStream:
    def __init__(self, tools_manager: ToolsManager):
        """
        Initializes the ingestion orchestrator.
        Acts as the 'dialer' for the expert committee.
        """
        self.tools = tools_manager
        self.state_manager = SystemStateManager()

    async def run_pipeline(self, asset_type: str, params: dict):
        """
        The main entry point for Track A.
        Follows the sequence: Parsing (Preparation) -> Unified Ingestion.
        """
        # Extract the unique ID to manage VRAM locking
        asset_id = params.get("asset_id") or params.get("video_id") or params.get("pdf_id")
        
        if not asset_id:
            return {"status": "error", "message": "Missing asset_id in parameters."}

        # 1. Resource Guard: Acquire global VRAM lock
        if not self.state_manager.acquire_ingestion_lock(task_id=asset_id):
            return {"status": "error", "message": "System VRAM is busy."}

        try:
            # 2. Sequential Dispatching (The Domino Effect)
            if asset_type == "video":
                # Step A: Slice & Audio Extraction -> Step B: Transcription
                await self._dispatch_video_workflow(params)
            elif asset_type == "pdf":
                # Step A: Document Parsing
                await self._dispatch_pdf_workflow(params)
            else:
                raise ValueError(f"Unsupported asset type: {asset_type}")

            # 3. Final Step: Unified Ingestion
            # All materials (Markdown/Frames/Transcripts) are now in storage/processed/
            logger.info(f"All materials ready. Triggering DataManager for indexing...")
            ingest_res = await asyncio.to_thread(
                self.tools.call_data_manager, 
                {"target": asset_type, "asset_id": asset_id}
            )
            return ingest_res

        except Exception as e:
            logger.error(f"Ingestion Pipeline Failure [{asset_id}]: {str(e)}")
            return {"status": "error", "message": str(e)}
        
        finally:
            # 4. Critical: Always release the lock to allow future tasks or querying
            self.state_manager.release_lock()

    async def _dispatch_video_workflow(self, params: dict):
        """Orchestrates Video Slicer then Whisper Node."""
        # Preparation Phase 1: Semantic Slicing
        # Note: params are passed directly to the wrapper
        res_slicer = await asyncio.to_thread(self.tools.call_video_slicer, params)
        if res_slicer.get("status") == "error":
            raise RuntimeError(f"VideoSlicer error: {res_slicer.get('details')}")

        # Preparation Phase 2: Audio Transcription
        # We construct the minimal dict required by whisper_node
        whisper_params = {"audio_id": params.get("video_id")}
        res_whisper = await asyncio.to_thread(self.tools.call_whisper_node, whisper_params)
        if res_whisper.get("status") == "error":
            raise RuntimeError(f"Whisper error: {res_whisper.get('details')}")

    async def _dispatch_pdf_workflow(self, params: dict):
        """Orchestrates PDF Parsing."""
        # Preparation Phase 1: Document Parsing
        res_parser = await asyncio.to_thread(self.tools.call_pdf_parser, params)
        if res_parser.get("status") == "error":
            raise RuntimeError(f"PDFParser error: {res_parser.get('details')}")