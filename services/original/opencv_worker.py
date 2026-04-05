import cv2
import yaml
import argparse
import logging
import subprocess
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [OpenCV-Worker] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("OpenCVWorker")

class OpenCVWorker:
    def __init__(self, global_cfg_path="configs/model_config.yaml", video_cfg_path="configs/video_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
            self.g_cfg = yaml.safe_load(f)
        with open(self.project_root / video_cfg_path, 'r', encoding='utf-8') as f:
            self.v_cfg = yaml.safe_load(f)['slicer']
        
        self.processed_root = Path(self.g_cfg['paths']['processed_storage']) / "video"

    def _save_uniform_frames(self, cap, frame_dir, target_count, fps, total_frames):
        logger.info(f"Triggering fallback: Uniformly sampling {target_count} frames.")
        step = max(total_frames // target_count, 1)
        saved_count = 0
        for i in range(0, total_frames, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret or saved_count >= target_count: break
            ts = i / fps
            cv2.imwrite(str(frame_dir / f"time_{ts:.2f}.jpg"), frame)
            saved_count += 1
        return saved_count

    def process_asset(self, asset_id, raw_path):
        output_folder = self.processed_root / asset_id
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # 1. 转码标准化 (找回详细日志)
        standard_mp4 = output_folder / f"{asset_id}.standard.mp4"
        if not standard_mp4.exists():
            logger.info(f"Standardizing video to H.264: {asset_id}")
            cmd = [
                "ffmpeg", "-y", "-i", str(raw_path),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k", str(standard_mp4)
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            logger.info("FFmpeg standardization complete.")

        # 2. 抽帧逻辑
        frame_dir = output_folder / "frames"
        frame_dir.mkdir(exist_ok=True)
        
        cap = cv2.VideoCapture(str(standard_mp4))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        
        prev_gray = None
        last_saved_time = -self.v_cfg['min_interval']
        saved_count = 0
        
        logger.info(f"Starting semantic slicing. Duration: {duration:.2f}s, Threshold: {self.v_cfg['frame_diff_threshold']}")

        for i in range(0, total_frames, int(fps / self.v_cfg['sample_rate'])):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret: break
            
            timestamp = i / fps
            gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
            
            if prev_gray is not None:
                score = cv2.absdiff(prev_gray, gray).mean() / 255.0
                if score > self.v_cfg['frame_diff_threshold'] and (timestamp - last_saved_time) > self.v_cfg['min_interval']:
                    cv2.imwrite(str(frame_dir / f"time_{timestamp:.2f}.jpg"), frame)
                    last_saved_time = timestamp
                    saved_count += 1
            else:
                # 存第一帧作为起始
                cv2.imwrite(str(frame_dir / f"time_{timestamp:.2f}.jpg"), frame)
                saved_count += 1
                
            prev_gray = gray

        # 3. 严谨性补帧 (找回老版本的 density 警告)
        min_expected = max(int(duration * (1/15)), 5)
        if saved_count < min_expected:
            logger.warning(f"Low density ({saved_count}/{min_expected}). Running uniform fallback.")
            saved_count = self._save_uniform_frames(cap, frame_dir, min_expected, fps, total_frames)
        else:
            logger.info(f"Semantic extraction successful: {saved_count} frames saved.")
        
        cap.release()
        print(f"SUCCESS|FRAME_COUNT:{saved_count}|STANDARD_PATH:{standard_mp4}")
        return saved_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset_id", required=True)
    parser.add_argument("--asset_raw_path", required=True)
    args = parser.parse_args()

    worker = OpenCVWorker()
    worker.process_asset(args.asset_id, args.asset_raw_path)