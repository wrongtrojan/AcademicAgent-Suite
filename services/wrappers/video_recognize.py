import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# 引入资产定义
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from core.assets_manager import AcademicAsset

def run_video_recognize(asset: AcademicAsset,timeout=1800):
    """
    重构后的编排器：
    1. 将 OpenCV 和 Whisper 的所有输出实时写入 logs/video_recognize.log
    2. 采用严格的行过滤逻辑提取 Worker 结果
    """
    WRAPPERS_DIR = Path(__file__).parent.absolute()
    ORIGINAL_DIR = WRAPPERS_DIR.parent / "original"
    PROJECT_ROOT = WRAPPERS_DIR.parent.parent
    
    # 日志路径设置
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    log_file_path = LOG_DIR / "video_recognize.log"
    
    python_exe = sys.executable

    try:
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n{'='*20} Video Task {asset.asset_id} Start: {datetime.now()} {'='*20}\n")
            
            # --- Stage 1: OpenCV 处理 ---
            log_file.write(f"[STAGE 1] Running OpenCVWorker...\n")
            cv_script = ORIGINAL_DIR / "opencv_worker.py"
            cv_cmd = [
                python_exe, "-u", str(cv_script), # -u 确保 stdout 无缓冲输出
                "--asset_id", asset.asset_id,
                "--asset_raw_path", asset.asset_raw_path
            ]
            
            cv_process = subprocess.Popen(
                cv_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(PROJECT_ROOT), bufsize=1
            )
            
            cv_success_line = None
            try:
                for line in cv_process.stdout:
                    log_file.write(f"[CV] {line}")
                    log_file.flush()
                    if line.startswith("SUCCESS"): cv_success_line = line.strip()
                cv_process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                cv_process.kill()
                raise Exception(f"OpenCV stage timed out after {timeout}s")
            if cv_process.returncode != 0 or not cv_success_line:
                raise Exception(f"OpenCVWorker failed with code {cv_process.returncode}")

            # 解析格式: SUCCESS|FRAME_COUNT:50|STANDARD_PATH:/path/xxx
            cv_parts = cv_success_line.split('|')
            frame_count = cv_parts[1].split(':')[1]
            standard_path = cv_parts[2].split(':')[1]

            # --- Stage 2: Whisper 处理 ---
            log_file.write(f"[STAGE 2] Running WhisperWorker...\n")
            ws_script = ORIGINAL_DIR / "whisper_worker.py"
            ws_cmd = [
                python_exe, "-u", str(ws_script),
                "--asset_id", asset.asset_id,
                "--asset_processed_path", str(Path(standard_path).parent)
            ]
            
            ws_process = subprocess.Popen(
                ws_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(PROJECT_ROOT), bufsize=1
            )
            
            ws_success_line = None
            for line in ws_process.stdout:
                log_file.write(f"[WS] {line}")
                log_file.flush()
                if line.startswith("SUCCESS"):
                    ws_success_line = line.strip()
            
            ws_process.wait()
            if ws_process.returncode != 0 or not ws_success_line:
                raise Exception(f"WhisperWorker failed with code {ws_process.returncode}")
                
            # 解析格式: SUCCESS|TRANSCRIPT_PATH:/path/xxx
            transcript_path = ws_success_line.split('|')[1].split(':')[1]

            log_file.write(f"{'='*20} Task {asset.asset_id} Completed {'='*20}\n")

            # --- 最终聚合结果 ---
            return {
                "status": "success",
                "asset_id": asset.asset_id,
                "frame_count": int(frame_count),
                "transcript_path": transcript_path,
                "processed_path": str(Path(standard_path).parent),
                "timestamp": datetime.now().isoformat()
            }

    except Exception as e:
        # 如果出错，也将错误信息写入日志
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(f"[CRITICAL ERROR] {str(e)}\n")
        return {
            "status": "error", 
            "asset_id": asset.asset_id, 
            "message": f"Orchestrator error: {str(e)}"
        }

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            asset_data = json.loads(sys.argv[1])
            # 统一标准：不再使用 asset_data['asset_id']
            asset_obj = AcademicAsset.from_dict(asset_data)
            print(json.dumps(run_video_recognize(asset_obj)))
        except Exception as e:
            print(json.dumps({"status": "error", "message": str(e)}))