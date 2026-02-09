import os
import json
import yaml
import torch
import logging
import numpy as np
from pathlib import Path
from PIL import Image
import torch.nn.functional as F
from transformers import CLIPProcessor, CLIPModel

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [VideoExpert] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("VideoMultimodalExpert")

class VideoMultimodalExpert:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent
        with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.processed_root = Path(self.config['paths']['processed_storage']) / "video"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self._model = None
        self._processor = None
        
        self.window_pre = 5.0
        self.window_post = 15.0

    @property
    def clip_resources(self):
        if self._model is None:
            model_path = self.config['model_paths']['clip']
            logger.info(f"--- Loading CLIP weights (Device: {self.device}): {model_path} ---")
            self._model = CLIPModel.from_pretrained(model_path, local_files_only=True).to(self.device)
            self._processor = CLIPProcessor.from_pretrained(model_path, local_files_only=True)
            self._model.eval()
        return self._model, self._processor

    def _get_aligned_embedding(self, outputs):
        tensor = None
        if hasattr(outputs, "image_embeds"):
            tensor = outputs.image_embeds
        elif hasattr(outputs, "text_embeds"):
            tensor = outputs.text_embeds
        elif hasattr(outputs, "pooler_output"):
            tensor = outputs.pooler_output
        
        if tensor is None:
            if hasattr(outputs, "last_hidden_state"):
                tensor = outputs.last_hidden_state.mean(dim=1)
            else:
                tensor = outputs[0] if isinstance(outputs, (list, tuple)) else outputs

        if hasattr(tensor, "detach"):
            if len(tensor.shape) == 1:
                tensor = tensor.unsqueeze(0)
            tensor = F.normalize(tensor, p=2, dim=-1)
            return tensor.detach().cpu().numpy().flatten().tolist()
        else:
            arr = np.array(tensor).flatten()
            norm = np.linalg.norm(arr)
            if norm > 1e-6:
                arr = arr / norm
            return arr.tolist()

    def _get_vec(self, text=None, image_path=None):
        model, processor = self.clip_resources
        try:
            with torch.no_grad():
                if text:
                    inputs = processor(text=[text], return_tensors="pt", padding=True, truncation=True).to(self.device)
                    outputs = model.get_text_features(**inputs)
                    return self._get_aligned_embedding(outputs)
                elif image_path:
                    image = Image.open(image_path).convert("RGB")
                    inputs = processor(images=image, return_tensors="pt").to(self.device)
                    outputs = model.get_image_features(**inputs)
                    return self._get_aligned_embedding(outputs)
        except Exception as e:
            logger.warning(f"Vectorization extraction failed: {e}")
            return None

    def process_all(self, force_reprocess=False):
        if not self.processed_root.exists():
            logger.error(f"Path does not exist: {self.processed_root}")
            return

        video_dirs = [d for d in self.processed_root.iterdir() if d.is_dir()]
        logger.info(f"🔍 Found {len(video_dirs)} video assets pending treatment...")

        for v_dir in video_dirs:
            output_json = v_dir / "alignment_metadata.json"
            if output_json.exists() and not force_reprocess:
                logger.info(f"⏭️  [SKIP] {v_dir.name} Binding data already exists.")
                continue

            transcript_p = v_dir / "transcript.json"
            frames_p = v_dir / "frames"
            
            if not transcript_p.exists() or not frames_p.exists():
                logger.warning(f"⚠️  Skipping {v_dir.name}: Missing prerequisite files.")
                continue

            self._process_single_video(v_dir, transcript_p, frames_p, output_json)

    def _process_single_video(self, v_dir, transcript_p, frames_p, output_json):
        logger.info(f"🚀 [START] Processing video: {v_dir.name}")
        
        with open(transcript_p, 'r', encoding='utf-8') as f:
            segments = json.load(f).get("segments", [])

        frame_files = sorted(list(frames_p.glob("*.jpg")), 
                            key=lambda x: float(x.stem.split('_')[1]))

        alignment_results = []

        total_frames = len(frame_files)
        for idx, img_path in enumerate(frame_files):
            ts = float(img_path.stem.split('_')[1])
            
            neighbor_texts = [s['text'] for s in segments 
                             if not (s['end'] < ts - self.window_pre or s['start'] > ts + self.window_post)]
            combined_text = " ".join(neighbor_texts).strip()

            img_vec = self._get_vec(image_path=img_path)
            text_vec = self._get_vec(text=combined_text) if combined_text else None

            is_critical = img_path.stem.startswith("time")
            need_vlm = True if (is_critical and len(combined_text) < 15) else False
            
            if idx % 10 == 0:
                logger.info(f"  Progress: {idx}/{total_frames} frames completed...")

            alignment_results.append({
                "frame_name": img_path.name,
                "timestamp": ts,
                "context_text": combined_text,
                "img_vector": img_vec,
                "text_vector": text_vec,
                "need_vlm_enhancement": need_vlm
            })

        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump({"video_id": v_dir.name, "alignments": alignment_results}, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ [DONE] {v_dir.name} Processing complete.")

if __name__ == "__main__":
    expert = VideoMultimodalExpert()
    expert.process_all()