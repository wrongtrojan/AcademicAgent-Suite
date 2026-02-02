import cv2
import yaml
import os
import sys
import subprocess
from pathlib import Path
import time
import logging

# --- 配置日志格式 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class VideoSlicer:
    def __init__(self, global_cfg_path="configs/model_config.yaml", video_cfg_path="configs/video_config.yaml"):
        self.project_root = Path(__file__).parent.parent.parent
        
        # 1. 加载配置
        try:
            with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
                self.g_cfg = yaml.safe_load(f)
            with open(self.project_root / video_cfg_path, 'r', encoding='utf-8') as f:
                self.v_cfg = yaml.safe_load(f)['slicer']
            logger.info("配置加载成功。")
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            sys.exit(1)
            
        # 2. 路径初始化
        self.raw_video_dir = Path(self.g_cfg['paths']['raw_storage']) / "video"
        self.processed_dir = Path(self.g_cfg['paths']['processed_storage']) / "video"
        
        self.raw_video_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"输入目录: {self.raw_video_dir}")
        logger.info(f"输出目录: {self.processed_dir}")

    def _should_process(self, video_path):
        video_id = video_path.stem
        target_folder = self.processed_dir / video_id
        standard_mp4 = target_folder / f"{video_id}.standard.mp4"
        frames_dir = target_folder / "frames"
        
        exists = standard_mp4.exists() and frames_dir.exists() and len(list(frames_dir.glob("*.jpg"))) > 0
        if exists:
            logger.info(f"检查增量: [{video_id}] 已存在处理结果，跳过。")
        else:
            logger.info(f"检查增量: [{video_id}] 属于新任务或不完整，开始处理。")
        return not exists

    def _preprocess_video(self, input_path):
        video_id = input_path.stem
        output_folder = self.processed_dir / video_id
        output_folder.mkdir(parents=True, exist_ok=True)
        output_mp4 = output_folder / f"{video_id}.standard.mp4"
        
        if output_mp4.exists():
            return output_mp4

        logger.info(f"--- 步骤1: 正在转码 (FFmpeg) -> {input_path.name} ---")
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-c:v', 'libx264', '-preset', 'superfast', '-crf', '23',
            '-c:a', 'aac', '-ar', '16000', '-ac', '1',
            '-movflags', '+faststart',
            str(output_mp4)
        ]
        
        start_t = time.time()
        try:
            # 这里的 stderr=subprocess.PIPE 可以捕获详细错误日志
            result = subprocess.run(cmd, capture_output=True, check=True)
            logger.info(f"转码完成，耗时: {time.time() - start_t:.2f}s")
            return output_mp4
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg 转码异常: {e.stderr.decode()}")
            return None

    def process_single_video(self, video_path):
        video_id = video_path.stem
        
        # 1. 格式标准化
        standard_video = self._preprocess_video(video_path)
        if not standard_video: return
        
        # 2. 准备输出目录
        output_folder = self.processed_dir / video_id
        frame_dir = output_folder / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        # 3. OpenCV 切片
        logger.info(f"--- 步骤2: 正在进行语义切片 (OpenCV) -> {video_id} ---")
        cap = cv2.VideoCapture(str(standard_video))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0: fps = 25
        
        last_saved_time = -self.v_cfg['min_interval']
        prev_gray = None
        count = 0
        saved_frames = 0
        start_t = time.time()

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            timestamp = count / fps
            # 每处理 20% 的进度打印一次日志
            if total_frames > 0 and count % (max(1, total_frames // 5)) == 0:
                percent = (count / total_frames) * 100
                logger.info(f"处理进度: {percent:.1f}% (当前时间点: {timestamp:.2f}s)")

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
        logger.info(f"切片完成: 提取 {saved_frames} 张关键帧, 耗时: {time.time() - start_t:.2f}s")

    def run_batch(self):
        valid_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.flv')
        video_files = [f for f in self.raw_video_dir.iterdir() if f.suffix.lower() in valid_extensions]
        
        if not video_files:
            logger.warning(f"在 {self.raw_video_dir} 未发现有效视频文件。")
            return

        logger.info(f"========= 启动批处理模式 (发现 {len(video_files)} 个视频) =========")
        
        for idx, v_file in enumerate(video_files):
            logger.info(f"\n[{idx+1}/{len(video_files)}] 任务对象: {v_file.name}")
            if self._should_process(v_file):
                try:
                    self.process_single_video(v_file)
                except Exception as e:
                    logger.error(f"处理视频 {v_file.name} 时发生未知错误: {e}")
            
        logger.info("========= 所有批处理任务已结束 =========")

if __name__ == "__main__":
    slicer = VideoSlicer()
    slicer.run_batch()