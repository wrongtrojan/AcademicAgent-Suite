import argparse
import json
import yaml
import sys
import logging
from pathlib import Path
from faster_whisper import WhisperModel

# 保持规范的日志输出
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [Whisper-Worker] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WhisperWorker")

class WhisperWorker:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        
        logger.info(f"Loading Whisper model from: {cfg['model_paths']['whisper']}")
        self.model = WhisperModel(
            cfg['model_paths']['whisper'], 
            device="cuda", 
            compute_type="float16",
            local_files_only=True
        )

    def transcribe(self, asset_id, processed_path):
        target_dir = Path(processed_path)
        # 对齐新版的文件命名规范
        video_path = target_dir / f"{asset_id}.standard.mp4"
        output_json = target_dir / "transcript.json"

        if not video_path.exists():
            raise FileNotFoundError(f"Standard video not found: {video_path}")

        # 找回老版本的优点：学术 Prompt + VAD 过滤
        academic_prompt = "这是一段学术讲解视频。请使用简体中文转录，确保专业术语（如算法、模型、参数等）准确。"
        
        logger.info(f"--- [START] Transcribing asset: {asset_id} ---")
        segments, info = self.model.transcribe(
            str(video_path), 
            beam_size=5, 
            language="zh",
            vad_filter=True, # 找回：过滤无声段落
            initial_prompt=academic_prompt # 找回：术语增强
        )
        
        logger.info(f"Detected language: {info.language} | Duration: {info.duration:.2f}s")

        results = []
        for s in segments:
            results.append({
                "start": round(s.start, 2), # 保持高精度
                "end": round(s.end, 2), 
                "text": s.text.strip()
            })
            # 找回：每20段打一次日志，方便监控进度
            if len(results) % 20 == 0:
                logger.info(f"Progress: {s.end:.1f}s transcribed...")

        output_data = {
            "asset_id": asset_id,
            "language": info.language,
            "duration": round(info.duration, 2),
            "segments": results
        }

        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        
        logger.info(f"--- [DONE] Transcript saved to: {output_json.name} ---")
        # 输出特定标记供 video_recognize 解析
        print(f"SUCCESS|TRANSCRIPT_PATH:{output_json}")
        return str(output_json)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset_id", required=True)
    parser.add_argument("--asset_processed_path", required=True)
    args = parser.parse_args()

    worker = WhisperWorker()
    worker.transcribe(args.asset_id, args.asset_processed_path)