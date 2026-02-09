import sys
import json
import os
from datetime import datetime
from pathlib import Path

try:
    from executor_logic import run_calculation
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from executor_logic import run_calculation

def main():
    CURRENT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_DIR.parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "sandbox.log"

    input_str = sys.argv[1] if len(sys.argv) > 1 else "{}"
    
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now()}] --- Sandbox Request Start ---\n")
        f.write(f"Raw Input: {input_str}\n")
        f.flush()

        try:
            params = json.loads(input_str)
            expr = params.get("expression", "")
            mode = params.get("mode", "eval")
            sym = params.get("symbol", "x")

            result = run_calculation(expr, mode, sym)
            
            output = {
                "status": "success",
                "result": result,
                "worker": "ScientificSandbox"
            }
            f.write(f"Execution Result: {result}\n")

        except Exception as e:
            output = {
                "status": "error", 
                "message": str(e),
                "worker": "ScientificSandbox"
            }
            f.write(f"Execution Error: {str(e)}\n")
        
        f.write(f"[{datetime.now()}] --- Sandbox Request End ---\n")

    print(json.dumps(output))

if __name__ == "__main__":
    main()