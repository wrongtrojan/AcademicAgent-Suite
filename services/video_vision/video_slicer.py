import cv2
import yaml
import sys
import subprocess
from pathlib import Path
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [VideoSlicer] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class VideoSlicer:
    def __init__(self, global_cfg_path="configs/model_config.yaml", video_cfg_path="configs/video_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        
        try:
            with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
                self.g_cfg = yaml.safe_load(f)
            with open(self.project_root / video_cfg_path, 'r', encoding='utf-8') as f:
                self.v_cfg = yaml.safe_load(f)['slicer']
            logger.info("uccessfully read global and video configurations.")
        except Exception as e:
            logger.error(f"Configuration file loading failed, please check path: {e}")
            sys.exit(1)
            
        self.raw_video_dir = Path(self.g_cfg['paths']['raw_storage']) / "video"
        self.processed_dir = Path(self.g_cfg['paths']['processed_storage']) / "video"
        
        self.raw_video_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _should_process(self, video_path):
        video_id = video_path.stem
        target_folder = self.processed_dir / video_id
        standard_mp4 = target_folder / f"{video_id}.standard.mp4"
        frames_dir = target_folder / "frames"
        
        exists = standard_mp4.exists() and frames_dir.exists() and len(list(frames_dir.glob("*.jpg"))) > 0
        if exists:
            logger.info(f"==== [SKIP] Incremental skip: {video_id} processing results already exist ====")
        return not exists

    def _preprocess_video(self, input_path):
        video_id = input_path.stem
        output_folder = self.processed_dir / video_id
        output_folder.mkdir(parents=True, exist_ok=True)
        output_mp4 = output_folder / f"{video_id}.standard.mp4"
        
        if output_mp4.exists():
            return output_mp4

        logger.info(f"--- [Step 1] Standardization Transcoding: {input_path.name} ---")
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-c:v', 'libx264', '-preset', 'superfast', '-crf', '23',
            '-c:a', 'aac', '-ar', '16000', '-ac', '1',
            '-movflags', '+faststart',
            str(output_mp4)
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return output_mp4
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg transcoding failed: {e.stderr.decode()}")
            return None

    def _save_uniform_frames(self, video_path, frame_dir, target_count):
        logger.warning(f"--- [Compensation Triggered] --- Insufficient keyframe density, supplementing to approx {target_count} frames")
        cap = cv2.VideoCapture(str(video_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        if total_frames <= 0 or fps <= 0: return

        step = total_frames // target_count
        if step <= 0: step = 1
        
        saved_count = 0
        for i in range(0, total_frames, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret: break
            
            timestamp = i / fps
            if not any(abs(float(f.stem.split('_')[1]) - timestamp) < 1.5 for f in frame_dir.glob("time_*.jpg")):
                save_path = frame_dir / f"uniform_{timestamp:.2f}.jpg"
                cv2.imwrite(str(save_path), frame)
                saved_count += 1
            
            if saved_count >= target_count: break
            
        cap.release()
        logger.info(f"Uniform compensation complete: Successfully captured {saved_count} sampling frames.")

    def process_single_video(self, video_path):
        video_id = video_path.stem
        
        standard_video = self._preprocess_video(video_path)
        if not standard_video: return
        
        output_folder = self.processed_dir / video_id
        frame_dir = output_folder / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"--- [Step 2] Semantic Slicing Analysis in progress: {video_id} ---")
        cap = cv2.VideoCapture(str(standard_video))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else 0
        
        logger.info(f"Video Info: Duration {duration_sec:.2f}s | FPS {fps}")
        
        last_saved_time = -self.v_cfg['min_interval']
        prev_gray = None
        count = 0
        saved_frames = 0
        start_t = time.time()

        report_step = max(int(total_frames / 5), 1)
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            timestamp = count / fps
            if count % report_step == 0 and count > 0:
                logger.info(f"Slicing progress: {timestamp:.1f} seconds of visual analysis completed...")
                
            if count % int(fps / self.v_cfg['sample_rate']) == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)
                
                if prev_gray is not None:
                    diff = cv2.absdiff(prev_gray, gray)
                    score = diff.mean() / 255.0
                    if score > self.v_cfg['frame_diff_threshold'] and (timestamp - last_saved_time) > self.v_cfg['min_interval']:
                        save_path = frame_dir / f"time_{timestamp:.2f}.jpg"
                        cv2.imwrite(str(save_path), frame)
                        last_saved_time = timestamp
                        saved_frames += 1
                prev_gray = gray
            count += 1
        cap.release()

        min_density = 1/15
        expected_min = max(int(duration_sec * min_density), 5) 

        if saved_frames < expected_min:
            logger.warning(f"Excessive static footage detected: Semantic slicing only yielded {saved_frames} frames, below academic syllabus requirements ({expected_min} frames)")
            self._save_uniform_frames(standard_video, frame_dir, target_count=expected_min)
        else:
            logger.info(f"Slicing density met: Extracted {saved_frames} key images via semantic slicing.")

        logger.info(f"Video [{video_id}] processing complete, total time: {time.time() - start_t:.2f}s")

    def run_batch(self):
        valid_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv')
        video_files = [f for f in self.raw_video_dir.iterdir() if f.suffix.lower() in valid_exts]
        
        if not video_files:
            logger.warning(f"No processable videos found in directory {self.raw_video_dir}.")
            return

        logger.info(f"========= ========= Starting Video Slicing Pipeline (Total {len(video_files)} tasks) =========")
        for v_file in video_files:
            if self._should_process(v_file):
                try:
                    self.process_single_video(v_file)
                except Exception as e:
                    logger.error(f"Exception occurred during task [{v_file.name}]: {e}")
        logger.info("========= All tasks completed =========")

if __name__ == "__main__":
    slicer = VideoSlicer()
    slicer.run_batch()
    