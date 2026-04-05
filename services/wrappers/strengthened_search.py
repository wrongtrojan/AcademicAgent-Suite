import sys
import json
from datetime import datetime
from pathlib import Path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from services.original.search_worker import AcademicSearchWorker

def main():
    # Setup Paths and Logging
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    log_file_path = LOG_DIR / "strengthened_search.log"

    # Redirect stderr/stdout to log file for traceability
    log_file = open(log_file_path, "a", encoding="utf-8")
    
    def log_event(message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file.write(f"[{timestamp}] {message}\n")
        log_file.flush()

    if len(sys.argv) < 2:
        error_msg = {"status": "error", "message": "No search parameters provided"}
        print(json.dumps(error_msg))
        return

    try:
        # Expected input format from Refiner: 
        # { "search_params": {...}, "preferences": {...}, "logic_intent": {...} }
        raw_input = json.loads(sys.argv[1])
        search_params = raw_input.get("search_params", {})
        preferences = raw_input.get("preferences", {})
        
        # Extract refined keywords and top_k
        keywords = " ".join(search_params.get("keywords", []))
        top_k = search_params.get("top_k", 8)
        
        log_event(f"New Search Request: Keywords='{keywords}', Preferences={preferences}")

        # Execution
        worker = AcademicSearchWorker()
        results = worker.search(
            query=keywords, 
            preferences=preferences, 
            top_k=top_k
        )
        
        log_event(f"Search successful. Hits returned: {len(results)}")
        
        # Output result to stdout for the calling process
        print(json.dumps({
            "status": "success",
            "results": results
        }))

    except Exception as e:
        log_event(f"CRITICAL ERROR: {str(e)}")
        print(json.dumps({"status": "error", "message": str(e)}))
    finally:
        log_file.close()

if __name__ == "__main__":
    main()