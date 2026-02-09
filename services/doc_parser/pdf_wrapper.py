import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_pdf_expert(params):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "doc_parser.log"
    shell_script = os.path.join(SCRIPT_DIR, "mineru_worker.sh")

    if not os.path.exists(shell_script):
        return {
            "status": "error", 
            "message": f"mineru_worker.sh not found in {SCRIPT_DIR}"
        }

    try:
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n{'='*20} Task Started: {datetime.now()} {'='*20}\n")
            log_file.flush()
            
            process = subprocess.Popen(
                ["bash", shell_script],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT)
            )
            
            process.wait()

        if process.returncode == 0:
            return {
                "status": "success",
                "log_file": str(log_file_path),
                "message": "DocParser task completed successfully"
            }
        else:
            return {
                "status": "error",
                "message": f"Shell script failed, exit code: {process.returncode}",
                "log_file": str(log_file_path)
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    input_str = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        params = json.loads(input_str)
        response = run_pdf_expert(params)
        print(json.dumps(response))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))