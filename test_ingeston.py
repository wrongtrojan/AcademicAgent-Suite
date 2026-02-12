import asyncio
import logging
from core.ingestion_stream import IngestionStream
from core.reasoning_stream import ReasoningStream
from core.tools_manager import ToolsManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [STREAM-TEST] - %(levelname)s - %(message)s')
logger = logging.getLogger("HybridTest")

async def run_hybrid_orchestration_test():
    tools = ToolsManager()
    ingestor = IngestionStream(tools)
    reasoner = ReasoningStream(tools)

    hybrid_params = {
        "asset_id": "math_analysis_chap4",
        "pdf_id": "math_analysis_pdf",
        "video_id": "differential_eq_video"
    }
    
    logger.info("🚀 PHASE 1: Launching 'ALL' mode ingestion stream...")
    ingest_task = asyncio.create_task(ingestor.run_pipeline(asset_type="all", params=hybrid_params))

    await asyncio.sleep(2) 
    logger.info("🛡️ PHASE 2: Testing VRAM guard during heavy 'all' mode ingestion...")
    collision_query = "What is the Wronski determinant?"
    intercepted_res = await reasoner.execute_query(collision_query, thread_id="collision_test_001")
    
    if intercepted_res.get("status") == "error":
        logger.info(f"✅ Confirmed: Reasoning stream intercepted. Message: {intercepted_res.get('message')}")

    await ingest_task
    logger.info("✅ PHASE 3: Ingestion stream finished. Lock released.")

    logger.info("🧠 PHASE 4: Testing hybrid reasoning (PDF + Video)...")
    complex_query = "Based on the text and video, explain the solution for a second-order linear differential equation with constant coefficients."
    
    final_output= await reasoner.execute_query(complex_query, thread_id="hybrid_reasoning_001")
    
    logger.info("--- Final Orchestration Audit ---")
    logger.info(f"Status: {final_output.get('status')}")
    logger.info(f"Evidence Anchors: {final_output.get('citations')}")
    logger.info(f"Reasoning Chain: {final_output.get('reasoning_chain')}")

if __name__ == "__main__":
    asyncio.run(run_hybrid_orchestration_test())