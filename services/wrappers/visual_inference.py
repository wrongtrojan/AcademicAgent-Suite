import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_visual_inference(params,timeout=600):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "visual_inference.log"
    logic_script = PROJECT_ROOT / "services" / "original" / "qwenvl_worker.py"

    image_path = params.get("image", "")
    if not os.path.exists(image_path):
        return {"status": "error", "message": f"Image not found at: {image_path}"}

    final_json_raw = ""
    
    try:
        process = subprocess.Popen(
            [sys.executable, "-u", str(logic_script), 
             "--image", str(image_path), 
             "--prompt", params.get("prompt", "")],
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1, 
            cwd=str(PROJECT_ROOT)
        )
        
        with open(log_file_path, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n{'='*20} Visual Inference Started: {datetime.now()} {'='*20}\n")
            
            capture_mode = False
            
            try:
                # 使用 iter 配合 readline 循环
                for line in iter(process.stdout.readline, ""):
                    log_f.write(line)
                    log_f.flush() 
                    if "--- RESULT_START ---" in line: capture_mode = True
                    elif "--- RESULT_END ---" in line: capture_mode = False
                    if capture_mode and "--- RESULT_START ---" not in line:
                        final_json_raw += line
                
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                return {"status": "error", "message": f"Inference timeout after {timeout}s"}
            log_f.write(f"{'='*20} Task Finished with exit code: {process.returncode} {'='*20}\n")

        if process.returncode == 0:
            if final_json_raw.strip():
                try:
                    return json.loads(final_json_raw.strip())
                except json.JSONDecodeError as je:
                    return {"status": "error", "message": f"JSON Decode Error: {str(je)}", "raw": final_json_raw}
            else:
                return {"status": "error", "message": "Logic layer returned empty result markers"}
        else:
            return {"status": "error", "message": f"Inference script crashed with code {process.returncode}"}

    except Exception as e:
        return {"status": "error", "message": f"Wrapper internal error: {str(e)}"}

if __name__ == "__main__":
    try:
        input_json = sys.argv[1] if len(sys.argv) > 1 else "{}"
        params = json.loads(input_json)
        
        response = run_visual_inference(params)

        sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
        sys.stdout.flush()
    except Exception as e:
        error_res = {"status": "error", "message": f"Wrapper entry point crash: {str(e)}"}
        print(json.dumps(error_res))