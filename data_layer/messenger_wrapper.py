import sys
import json
import logging
from pathlib import Path
from json_messenger import JsonMessenger

def main():
    # 1. 路径初始化
    SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = SCRIPT_DIR.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    LOG_FILE = LOG_DIR / "json_messenger.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8')
        ]
    )
    script_logger = logging.getLogger("Main")
    
    input_str = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        params = json.loads(input_str)
    except Exception as e:
        error_msg = {"status": "error", "message": f"Invalid JSON input: {str(e)}"}
        print(json.dumps(error_msg))
        return

    mode = params.get("mode", "unknown")
    result = {"status": "error", "message": "Unknown mode"}

    try:
        script_logger.info(f"{'='*20} Messenger Task ({mode}) Started {'='*20}")
        
        messenger = JsonMessenger(PROJECT_ROOT)
        
        if mode == "come":
            script_logger.info("Initiating global scan for increments...")
            tasks = messenger.scan_increments()
            
            script_logger.info(f"Scan complete. Found {len(tasks)} pending tasks.")
            for t in tasks:
                script_logger.info(f"    - ID: {t['asset_id']} | Type: {t['asset_type']}")
            
            result = {"status": "success", "tasks": tasks}
            
        elif mode == "back":
            asset_id = params.get("asset_id")
            asset_type = params.get("asset_type")
            content = params.get("content")
            
            script_logger.info(f"Archiving result for {asset_type} ID: {asset_id}")
            save_path = messenger.messenger_back(asset_id, asset_type, content)
            
            script_logger.info(f"Data persisted to: {save_path}")
            result = {"status": "success", "save_path": save_path}
            
        else:
            script_logger.error(f"Unsupported mode: {mode}")

        script_logger.info(f"{'='*20} Messenger Task Finished {'='*20}")

    except Exception as e:
        script_logger.critical(f"Execution failed: {str(e)}", exc_info=True)
        result = {"status": "error", "message": str(e)}

    sys.stdout.flush() 
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()