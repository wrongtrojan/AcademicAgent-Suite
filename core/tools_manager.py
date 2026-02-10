import subprocess
import json
import os
import yaml
import logging
import time
from pathlib import Path
from core.system_state import SystemStateManager, SystemStatus

# Global directory for log assets
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Console logging configuration for ToolsManager
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [TOOLS-MANAGER] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ToolsManager")

class ToolsManager:
    def __init__(self, config_path="configs/model_config.yaml"):
        """
        Initialize the multi-environment gateway.
        """
        self.project_root = Path(__file__).resolve().parent.parent
        full_config_path = self.project_root / config_path
        
        with open(full_config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.envs = self.config.get('environments', {})
        self.state_manager = SystemStateManager()
        self.expert_log_path = LOG_DIR / "tools_expert.log"
        
        logger.info("Resource-Aware Toolbox initialized. VRAM monitoring active.")

    def _dispatch_subprocess(self, env_key, script_rel_path, params=None, task_type=SystemStatus.INGESTING):
        """
        Low-level subprocess dispatcher with Non-Interference logging principle.
        Logs only metadata to tools_expert.log; business logs are handled internally by services.
        """
        # 1. Resource Guard: Prevent VRAM collisions during ingestion
        if task_type == SystemStatus.QUERYING and self.state_manager.get_status == SystemStatus.INGESTING:
            logger.error(f"VRAM Collision: {script_rel_path} blocked by active ingestion.")
            return {"status": "error", "message": "VRAM locked by ingestion."}

        python_exe = self.envs.get(env_key)
        script_path = self.project_root / script_rel_path
        
        if not python_exe or not os.path.exists(python_exe):
            logger.error(f"Environment Error: Interpreter not found for {env_key}.")
            return {"status": "error", "message": f"Invalid env: {env_key}"}

        current_env = os.environ.copy()
        
        venv_bin = str(Path(python_exe).parent)
        
        current_env["PATH"] = f"{venv_bin}:/usr/bin:/usr/local/bin:{current_env.get('PATH', '')}"
        
        current_env["PYTHONUNBUFFERED"] = "1"

        json_params = json.dumps(params if params else {}, ensure_ascii=False)
        start_time = time.time()

        try:
            process = subprocess.Popen(
                [python_exe, str(script_path), json_params],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.project_root),
                env=current_env 
            )
            # ------------------------------------------
            
            stdout, stderr = process.communicate()
            duration = time.time() - start_time

            # 3. Metadata-Only Logging (Non-Interference)
            with open(self.expert_log_path, 'a', encoding='utf-8') as f:
                log_entry = (
                    f"--- [SUBPROCESS_INVOCATION] ---\n"
                    f"Timestamp: {time.ctime()}\n"
                    f"Script: {script_rel_path}\n"
                    f"Params: {json_params}\n"
                    f"Exit_Code: {process.returncode}\n"
                    f"Duration: {duration:.2f}s\n"
                    f"-------------------------------\n"
                )
                f.write(log_entry)

            if process.returncode != 0:
                logger.error(f"Expert Execution Failed: {script_rel_path}")
                return {"status": "error", "details": stderr.strip()}

            # 4. Result Extraction: Capture the last line as JSON output
            output_lines = [l for l in stdout.strip().split('\n') if l.strip()]
            if not output_lines:
                return {"status": "error", "message": "No output from expert script."}
            
            try:
                return json.loads(output_lines[-1])
            except json.JSONDecodeError:
                return {"status": "success", "raw_output": output_lines[-1]}

        except Exception as e:
            logger.error(f"Dispatch Exception: {str(e)}")
            return {"status": "error", "message": str(e)}

    # ================= EXPERT INTERFACES (Wrappers) ==================

    def call_data_manager(self, params: dict):
        """Final Step: DataStreamOrchestrator for vectorization."""
        logger.info(f"🚀 [Data Pipeline] Launching manager...")
        return self._dispatch_subprocess("data_layer", "data_layer/data_wrapper.py", params)

    def call_searcher(self, params: dict):
        """Querying: Vector search across Milvus indices."""
        logger.info(f"🔍 [Vector Search] Dispatching searcher for query...")
        return self._dispatch_subprocess(
            "data_layer", "data_layer/search_wrapper.py", params, 
            task_type=SystemStatus.QUERYING
        )

    def call_video_slicer(self, params: dict):
        """Parsing: Video frame and audio extraction."""
        logger.info(f"✂️ [Video Slicer] Processing video...")
        return self._dispatch_subprocess("video_slicer", "services/video_vision/video_wrapper.py", params)

    def call_whisper_node(self, params: dict):
        """Parsing: Audio to text transcription."""
        logger.info(f"👂 [Audio Expert] Processing audio...")
        return self._dispatch_subprocess("audio_pro", "services/audio_pro/audio_wrapper.py", params)

    def call_pdf_parser(self, params: dict):
        """Parsing: MinerU structured document extraction."""
        logger.info(f"📄 [Doc Parser] Processing PDF...")
        return self._dispatch_subprocess("doc_parser", "services/doc_parser/pdf_wrapper.py", params)

    def call_sandbox(self, params: dict):
        """Reasoning: Code and symbolic verification."""
        logger.info(f"🔢 [Sandbox] Computing...")
        return self._dispatch_subprocess(
            "sandbox", "services/sandbox/sandbox_wrapper.py", params,
            task_type=SystemStatus.QUERYING
        )