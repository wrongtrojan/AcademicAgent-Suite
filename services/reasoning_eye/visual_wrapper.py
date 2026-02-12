import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_visual_inference(params):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "resoning_eye.log"
    logic_script = os.path.join(SCRIPT_DIR, "qwen_inference.py")

    try:
        with open(log_file_path, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n{'='*20} Visual Inference Started: {datetime.now()} {'='*20}\n")
            log_f.flush()
            process = subprocess.Popen(
                [sys.executable, "-u", str(logic_script), 
                 "--image", params.get("image", ""), 
                 "--prompt", params.get("prompt", "")],
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,     
                text=True,
                cwd=str(PROJECT_ROOT)
            )
            
            final_json_raw = ""
            capture_mode = False

            for line in process.stdout:
                log_f.write(line) 
                log_f.flush()
                if "--- RESULT_START ---" in line:
                    capture_mode = True
                    continue
                if "--- RESULT_END ---" in line:
                    capture_mode = False
                    continue
                if capture_mode:
                    final_json_raw += line
            
            process.wait()

        log_f.write(f"{'='*20} Task Finished with exit code: {process.returncode} {'='*20}\n")
        
        if process.returncode == 0 and final_json_raw:
            return json.loads(final_json_raw.strip())
        else:
            return {"status": "error", "message": "Logic layer did not return a valid result"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    try:
        input_json = sys.argv[1] if len(sys.argv) > 1 else "{}"
        params = json.loads(input_json)
        
        response = run_visual_inference(params)

        sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Wrapper entry point crash: {str(e)}"}))