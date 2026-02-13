import asyncio
import logging
import sys
from pathlib import Path

# 将项目根目录添加到系统路径，确保能导入 core 和 data_layer
root_path = Path(__file__).resolve().parent.parent
sys.path.append(str(root_path))

from core.ingestion_stream import IngestionStream
from core.tools_manager import ToolsManager

# 配置日志输出格式，与 IngestionStream 的符号系统对齐
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("TestLauncher")

async def run_final_ingestion_test():
    """
    [Final Verification] 测试 ID 无感化的全量同步流程
    """
    logger.info("🧪 [Test] Starting Final Orchestration Test (ID-Agnostic)...")
    
    # 1. 初始化组件
    # 注意：ToolsManager 内部会通过 Python 调用各个 Wrapper
    tools = ToolsManager()
    ingestor = IngestionStream(tools)

    logger.info("📡 [Test] Triggering Global Sync. No asset_id needed.")
    
    try:
        # 2. 执行核心同步逻辑
        # 该操作会依次：
        #   - 扫描并解析 PDF/视频 (生数据入库)
        #   - 巡检 messenger 获取增量列表
        #   - 调 DeepSeek 生成 JSON 大纲
        #   - 回传归档至各自的 summary_outline.json
        await ingestor.run_global_sync()
        
        logger.info("🏁 [Test] Global Sync call finished.")
        
        # 3. 验证建议 (人工核查)
        logger.info("-" * 50)
        logger.info("🔍 [Audit Suggestion] Please check the following locations for outputs:")
        logger.info(f"1. Video Outlines: storage/processed/video/*/summary_outline.json")
        logger.info(f"2. PDF Outlines:   storage/processed/magic-pdf/*/summary_outline.json")
        logger.info("-" * 50)

    except Exception as e:
        logger.error(f"❌ [Test Failure] Something went wrong: {str(e)}")

if __name__ == "__main__":
    # 确保在异步环境下运行
    asyncio.run(run_final_ingestion_test())