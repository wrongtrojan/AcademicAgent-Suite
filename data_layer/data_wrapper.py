import subprocess
import sys
import time
import logging
from pathlib import Path

class DataManager:
    """
    Data Ingestion Orchestrator:
    Captures detailed logs from subprocesses into logs/data_layer_log.txt
    """
    def __init__(self, log_rel_path="logs/data_layer.log"):
        self.project_root = Path(__file__).resolve().parent.parent
        self.python_exe = sys.executable
        
        # Ensure log directory exists
        self.log_path = self.project_root / log_rel_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup Manager Logger (For high-level orchestration)
        self.logger = logging.getLogger("DataManager")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - [DATA-MANAGER] - %(levelname)s - %(message)s')

        # Console Handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # File Handler (Main Log File)
        fh = logging.FileHandler(self.log_path, mode='a', encoding='utf-8')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        self.logger.info(f"DataManager initialized. Logs will be exported to: {self.log_path}")

    def run_ingestion_pipeline(self, target_type="all", force_reset=False):
        start_time = time.time()
        self.logger.info(f"========= Starting Ingestion Pipeline (Target: {target_type}) =========")

        try:
            # 1. PDF Vectorization
            if target_type in ["pdf", "all"]:
                self._execute_step("PDF Vectorization", "data_layer/clip_worker_pdf.py")

            # 2. Video Vectorization
            if target_type in ["video", "all"]:
                self._execute_step("Video Vectorization", "data_layer/clip_worker_video.py")

            # 3. Milvus Ingestion
            ingest_args = ["--force_reset"] if force_reset else []
            self._execute_step("Database Ingestion", "data_layer/milvus_ingestor.py", ingest_args)

            elapsed = time.time() - start_time
            self.logger.info(f"========= Pipeline Completed Successfully in {elapsed:.2f}s =========")
            return {"status": "success"}

        except Exception as e:
            self.logger.error(f"!!! Pipeline Aborted: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _execute_step(self, step_name, script_rel_path, args=None):
        """Executes a script and pipes its output directly to the log file."""
        self.logger.info(f"--- [START] {step_name} ---")
        script_path = self.project_root / script_rel_path
        
        cmd = [self.python_exe, str(script_path)]
        if args:
            cmd.extend(args)

        # Use 'with' to ensure the log file is properly flushed
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*20} Subprocess Log: {script_rel_path} {'='*20}\n")
            f.flush()

            # Execute and redirect both stdout and stderr to the file
            process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=f,
                text=True,
                cwd=str(self.project_root)
            )
            process.wait()

            if process.returncode != 0:
                f.write(f"\n[ERROR] Subprocess exited with code {process.returncode}\n")
                self.logger.error(f"{step_name} failed. Check {self.log_path} for details.")
                raise RuntimeError(f"Step failed: {step_name}")

        self.logger.info(f"--- [FINISHED] {step_name} ---")
        self._cool_down()

    def _cool_down(self):
        time.sleep(1.5)

if __name__ == "__main__":
    manager = DataManager()
    manager.run_ingestion_pipeline(target_type="all")