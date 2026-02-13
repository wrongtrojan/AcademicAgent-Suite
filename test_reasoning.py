import asyncio
import logging
import os
import redis.asyncio as redis
from core.reasoning_stream import ReasoningStream
from core.tools_manager import ToolsManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [QA-AUDIT] - %(levelname)s - %(message)s')
logger = logging.getLogger("AdvancedTest")

async def run_reflective_test():
    tools = ToolsManager()
    reasoner = ReasoningStream(tools)
    
    # 强制引导到视频资产的测试用例
    # 建议选取一个你确定库里有的视频名称
    test_query = "在视频 360 秒左右，屏幕上写了什么？"
    thread_id = "vlm_stress_test_002" 

    logger.info("🚀 STARTING VLM-FOCUSED TEST...")

    try:
        result = await reasoner.execute_query(test_query, thread_id=thread_id)
        
        # 核心观察点：Node 路由
        chain = result.get("reasoning_chain", [])
        has_vlm = any("vision_eye" in str(s).lower() or "视觉" in str(s) for s in chain)
        
        if has_vlm:
            logger.info("✅ SUCCESS: VLM Node (vision_eye) was TRIPPED.")
            logger.info(f"📸 VLM Output Snippet: {result.get('vlm_feedback')}")
        else:
            logger.warning("❌ FAILURE: VLM Node was BYPASSED.")
            # 进一步诊断：看看检索到了什么
            docs = result.get("retrieved_docs", [])
            video_docs = [d for d in docs if d['metadata'].get('modality') == 'video']
            logger.info(f"📊 Debug Info: Retrieved {len(video_docs)} video chunks.")
            
        # 检查是否因为 intent_check 判定不需要视觉
        if not result.get("has_video") and video_docs:
            logger.error("⚠️ CRITICAL: Video docs exist but 'has_video' flag is False. Check intent_check logic.")

    except Exception as e:
        logger.error(f"💥 Test Crashed: {e}")

if __name__ == "__main__":
    asyncio.run(run_reflective_test())