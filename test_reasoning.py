import asyncio
import logging
import os
import redis.asyncio as redis # 使用异步 Redis 客户端对齐 AsyncRedisSaver
from pathlib import Path
from core.reasoning_stream import ReasoningStream
from core.tools_manager import ToolsManager
from core.system_state import SystemStateManager

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [BATTLE-TEST] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("RealEngineTest")

async def run_connectivity_test():
    tools = ToolsManager()
    reasoner = ReasoningStream(tools)
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        r = redis.from_url(redis_url)
        await r.ping()
        logger.info(f"✅ Redis Physical Connection: OK ({redis_url})")
        await r.close()
    except Exception as e:
        logger.error(f"❌ Redis Connection Failed: {e}. Ensure docker container is running.")
        return

    test_query = "你能不能告诉我pdf第一面例题2.1的解决方法"
    thread_id = "test_session_001_real" 

    logger.info(f"🧠 Starting Real-World Reasoning Test. Thread: {thread_id}")

    try:
        result = await reasoner.execute_query(test_query, thread_id=thread_id)
    except Exception as e:
        logger.error(f"❌ Execution crashed: {str(e)}")
        return

    logger.info("--- 🛡️ Physical Connectivity Audit ---")

    if result.get("status") == "completed":
        logger.info("✅ Workflow Logic: COMPLETED")
    else:
        logger.error(f"❌ Workflow Logic: {result.get('status')} (Msg: {result.get('message', 'N/A')})")

    citations = result.get("citations", [])
    pdf_cites = [c for c in citations if c["type"] == "pdf"]
    if pdf_cites and all("bbox" in c and c["bbox"] for c in pdf_cites):
        logger.info(f"✅ BBox Data Link: SUCCESS (Found {len(pdf_cites)} coordinates)")
    else:
        logger.warning("⚠️ BBox Data Link: EMPTY (Metadata might missing coordinates in Milvus)")

    vlm_feedback = result.get("vlm_feedback", "")
    if vlm_feedback and "skipped" not in result.get("status", ""):
        logger.info(f"✅ VLM Execution: SUCCESS (Output: {vlm_feedback[:50]}...)")
    else:
        logger.warning("⚠️ VLM Execution: SKIPPED or FAILED (Check frame path or intent_check)")

    logic_res = result.get("verification_results", "")
    if "Verified:" in logic_res:
        logger.info(f"✅ Sandbox Execution: SUCCESS (Result: {logic_res})")
    else:
        logger.warning("⚠️ Sandbox Execution: NO FORMULA VERIFIED")

    from langgraph.checkpoint.redis import AsyncRedisSaver
    async with AsyncRedisSaver.from_conn_string(redis_url) as saver:
        checkpoint = await saver.aget({"configurable": {"thread_id": thread_id}})
        if checkpoint:
            logger.info("✅ Redis Checkpointer: SUCCESS (State persisted)")
        else:
            logger.error("❌ Redis Checkpointer: FAILED (No checkpoint found)")
    
    logger.info("="*50)
    logger.info("🎓 DEEPSEEK FINAL ACADEMIC ANSWER:")
    print(result.get("final_answer")) 
    logger.info("="*50)

    logger.info("--- End of Audit ---")

if __name__ == "__main__":
    asyncio.run(run_connectivity_test())