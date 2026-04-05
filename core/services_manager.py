import asyncio
import json
import os
import yaml
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from core.assets_manager import AcademicAsset

# Global directory for log assets
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Console logging configuration for ToolsManager
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [SERVICES-MANAGER] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ServicesManager")

class ServicesManager:
    def __init__(self, config_path="configs/model_config.yaml"):
        """
        Initialize the multi-environment gateway.
        """
        self.project_root = Path(__file__).resolve().parent.parent
        full_config_path = self.project_root / config_path
        
        with open(full_config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.envs = self.config.get('environments', {})
        self.expert_log_path = LOG_DIR / "services.log"
        self.wrapper_dir = self.project_root / "services" / "wrappers"
        

    async def _dispatch_async(self, env_key: str, script_name: str, asset: Optional[AcademicAsset] = None, params: Optional[Dict] = None, timeout: int = 3600) -> Dict[str, Any]:
        """
        核心异步分派逻辑：启动子进程，等待并解析返回的 JSON 结果
        """
        python_exe = self.envs.get(env_key)
        script_path = self.wrapper_dir / script_name

        if not python_exe or not os.path.exists(python_exe):
            return {"status": "error", "message": f"Python interpreter not found for env: {env_key}"}
        
        if not script_path.exists():
            return {"status": "error", "message": f"Wrapper script not found: {script_name}"}

        current_env = os.environ.copy()
        
        venv_bin = str(Path(python_exe).parent)
        
        current_env["PATH"] = f"{venv_bin}{os.pathsep}{current_env.get('PATH', '')}"
        
        current_env["PYTHONUNBUFFERED"] = "1"
        
        # 准备参数
        input_data = {}
        if asset:
            input_data = asset.to_dict()
        if params:
            input_data.update(params)
        
        input_str = json.dumps(input_data)

        logger.info(f"Dispatching task to [{env_key}] -> {script_name} (Asset: {asset.asset_id if asset else 'N/A'})")

        try:
            # 启动异步子进程
            process = await asyncio.create_subprocess_exec(
                python_exe, "-u", str(script_path), input_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_root),
                env=current_env
            )

            # 等待任务完成并设置超时
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                return {"status": "error", "message": f"Task timed out after {timeout}s", "asset_id": asset.asset_id if asset else None}

            # 解码输出
            out_str = stdout.decode().strip()
            err_str = stderr.decode().strip()

            if process.returncode != 0:
                logger.error(f"Task failed with exit code {process.returncode}. Stderr: {err_str}")
                return {
                    "status": "error", 
                    "exit_code": process.returncode, 
                    "message": err_str,
                    "asset_id": asset.asset_id if asset else None
                }

            # 尝试解析输出的最后一行作为 JSON (Worker 通常在最后打印结果)
            try:
                # 过滤掉中间可能的打印信息，只取最后一行非空行
                last_line = out_str.splitlines()[-1] if out_str else "{}"
                result = json.loads(last_line)
                logger.info(f"Task completed successfully: {script_name}")
                return result
            except (json.JSONDecodeError, IndexError):
                return {
                    "status": "partial_success", 
                    "raw_output": out_str, 
                    "message": "Task finished but output was not valid JSON"
                }

        except Exception as e:
            logger.exception(f"Unexpected error during dispatch: {str(e)}")
            return {"status": "error", "message": str(e)}

    # --- 异步服务接口实现 ---

    async def start_pdf_recognition(self, asset: AcademicAsset):
        """PDF 解析服务"""
        return await self._dispatch_async("doc_recognize", "pdf_recognize.py", asset=asset)

    async def start_video_recognition(self, asset: AcademicAsset):
        """视频解析服务"""
        return await self._dispatch_async("video_recognize", "video_recognize.py", asset=asset)

    async def start_clip_indexing(self, asset: AcademicAsset):
        """特征提取"""
        return await self._dispatch_async("data_stream", "clip_work.py", asset=asset)

    async def start_milvus_ingestion(self, asset: AcademicAsset):
        """数据入库"""
        return await self._dispatch_async("data_stream", "milvus_ingest.py", asset=asset)

    async def start_structure_generation(self, asset: AcademicAsset):
        """DeepSeek 结构化输出"""
        return await self._dispatch_async("agent_logic", "structure_generate.py", asset=asset)

    async def call_visual_expert(self,  params: dict):
        """Qwen-VL 视觉推理"""
        return await self._dispatch_async("visual_inference", "visual_inference.py", params=params)
    
    async def call_sandbox_expert(self, params: dict):
        """沙盒推理"""
        return await self._dispatch_async("sandbox_inference", "sandbox_inference.py", params=params)
    
    async def start_academic_search(self, params: dict):
        """学术搜索"""
        return await self._dispatch_async("data_stream", "strengthened_search.py", params=params)