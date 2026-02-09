import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_whisper(params):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "audio_pro.log"
    logic_script = os.path.join(SCRIPT_DIR, "whisper_node.py")
    python_exe = sys.executable

    try:
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n{'='*20} Whisper Task Started: {datetime.now()} {'='*20}\n")
            log_file.flush()

            process = subprocess.Popen(
                [python_exe, "-u", logic_script], 
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT)
            )

            process.wait()

        if process.returncode == 0:
            return {
                "status": "success",
                "worker": "Whisper-Node",
                "log_file": str(log_file_path),
                "message": "Audio transcription pipeline execution complete"
            }
        else:
            return {
                "status": "error",
                "message": f"Whisper expert execution abnormal, exit code: {process.returncode}",
                "log_file": str(log_file_path)
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    try:
        input_data = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
        response = run_whisper(input_data)
        print(json.dumps(response))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))