import os
import sys
import json
import yaml
import torch
import numpy as np
from PIL import Image
from pathlib import Path
from datetime import datetime
import torch.nn.functional as F
from transformers import CLIPProcessor, CLIPModel

# --- 基础日志函数 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file_path = LOG_DIR / "clip_work.log"

def log_message(level, msg):
    """最基础的日志重定向：同时打印到控制台并追加到文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    formatted_msg = f"{timestamp} - [CLIPWork] - {level} - {msg}"
    
    # 输出到控制台
    print(formatted_msg)
    
    # 追加到文件
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(formatted_msg + "\n")

# --- 屏蔽 tqdm ---
import tqdm
class DisabledTqdm:
    def __init__(self, *args, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args, **kwargs): pass
    def __iter__(self): return self
    def __next__(self): raise StopIteration
    def __getattr__(self, name): return lambda *args, **kwargs: None
tqdm.tqdm = DisabledTqdm

# 注入项目根目录
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from core.assets_manager import AcademicAsset, AssetType

class CLIPWorker:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        self.project_root = PROJECT_ROOT
        with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        model_id = self.config['model_paths']['clip']
        log_message("INFO", f"Loading CLIP model on {self.device}...")
        
        self.model = CLIPModel.from_pretrained(model_id).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_id)
        
        self.window_pre = 5.0
        self.window_post = 15.0

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
    
    def _get_vec(self, image_path=None, text=None):
        try:
            with torch.no_grad():
                if image_path:
                    image = Image.open(image_path).convert("RGB")
                    inputs = self.processor(images=image, return_tensors="pt").to(self.device)
                    outputs = self.model.get_image_features(**inputs)
                elif text:
                    inputs = self.processor(text=[text], return_tensors="pt", padding=True, truncation=True).to(self.device)
                    outputs = self.model.get_text_features(**inputs)
                else:
                    return None
                return self._get_aligned_embedding(outputs)
        except Exception as e:
            log_message("WARNING", f"Embedding error: {e}")
            return None

    def _process_pdf(self, asset: AcademicAsset):
        clean_name = asset.asset_id.replace(".pdf", "")
        base_dir = Path(self.config['paths']['processed_storage']) / "magic-pdf" / clean_name
        
        middle_json = None
        ocr_dir = None
        for sub in ["auto", "ocr"]:
            potential_dir = base_dir / sub
            possible_files = [potential_dir / f"{clean_name}_middle.json"]
            for pf in possible_files:
                if pf.exists():
                    middle_json = pf
                    ocr_dir = potential_dir
                    break
            if middle_json: break

        if not middle_json:
            found = list(base_dir.glob("**/*_middle.json"))
            if found:
                middle_json = found[0]
                ocr_dir = middle_json.parent
            else:
                raise FileNotFoundError(f"MinerU middle.json not found in {base_dir}")

        log_message("INFO", f"Found middle.json at: {middle_json}")
        
        doc_results = {"images": {}, "text_chunks": []}
        with open(middle_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        pages = data.get("pdf_info") or data.get("pdf_intermediate_dict") or []

        for page_idx, page_info in enumerate(pages):
            blocks = page_info.get("preproc_blocks") or page_info.get("middle_blocks") or []
            for block in blocks:
                block_type = block.get("type", "")
                block_bbox = block.get("bbox", [])

                if block_type in ["image", "table"]:
                    img_relative_dir = None
                    caption = ""
                    for sub_block in block.get("blocks", []):
                        for line in sub_block.get("lines", []):
                            for span in line.get("spans", []):
                                if "image_path" in span:
                                    img_relative_dir = span["image_path"]
                                if "content" in span and span.get("type") == "text":
                                    caption += span["content"]
                    
                    if img_relative_dir:
                        full_img_path = ocr_dir / "images" / img_relative_dir
                        if full_img_path.exists():
                            embedding = self._get_vec(image_path=full_img_path)
                            if embedding:
                                img_name = Path(img_relative_dir).name
                                doc_results["images"][img_name] = {
                                    "type": block_type, "page_idx": page_idx,
                                    "text_slice": caption[:50], "embedding": embedding, "bbox": block_bbox 
                                }
                else:
                    full_text = ""
                    lines = block.get("lines", [])
                    if lines:
                        for line in lines:
                            for span in line.get("spans", []):
                                full_text += span.get("content", "")
                    else:
                        full_text = block.get("text") or block.get("text_content") or ""

                    if len(full_text.strip()) >= 5:
                        embedding = self._get_vec(text=full_text)
                        if embedding:
                            doc_results["text_chunks"].append({
                                "type": block_type or "text", "page_idx": page_idx,
                                "text_slice": full_text[:50], "embedding": embedding, "bbox": block_bbox 
                            })

        output_path = base_dir / "clip_features.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(doc_results, f, ensure_ascii=False, indent=4)
        return len(doc_results["text_chunks"]) + len(doc_results["images"])

    def _process_video(self, asset: AcademicAsset):
        base_dir = Path(self.config['paths']['processed_storage']) / "video" / asset.asset_id
        frame_dir = base_dir / "frames"
        transcript_path = base_dir / "transcript.json"

        log_message("INFO", f"Processing Video asset: {asset.asset_id}")

        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript missing for {asset.asset_id}")

        with open(transcript_path, 'r', encoding='utf-8') as f:
            segments = json.load(f).get("segments", [])

        frame_files = sorted(list(frame_dir.glob("*.jpg")), 
                    key=lambda x: float(x.stem.split('_')[1]) if '_' in x.stem else x.name)
        results = []

        for img_path in frame_files:
            try:
                ts = float(img_path.stem.split('_')[1])
            except: continue

            neighbor_texts = [s['text'] for s in segments 
                             if not (s['end'] < ts - self.window_pre or s['start'] > ts + self.window_post)]
            combined_text = " ".join(neighbor_texts).strip()

            img_vec = self._get_vec(image_path=img_path)
            text_vec = self._get_vec(text=combined_text) if combined_text else None

            results.append({
                "timestamp": ts, "frame_name": img_path.name,
                "img_vector": img_vec, "text_vector": text_vec,
                "content": combined_text, "need_vlm": True if (len(combined_text) < 15) else False
            })

        output_path = base_dir / "clip_features.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        return len(results)

def run_clip_work(asset: AcademicAsset):
    log_message("INFO", f"{'='*20} CLIP Task {asset.asset_id} Start {'='*20}")
    try:
        worker = CLIPWorker()
        if asset.asset_type == AssetType.PDF:
            count = worker._process_pdf(asset)
        elif asset.asset_type == AssetType.VIDEO:
            count = worker._process_video(asset)
        else:
            raise ValueError(f"Unsupported asset type: {asset.asset_type}")
        
        log_message("INFO", f"SUCCESS: Generated {count} vectors for {asset.asset_id}")
        return {"status": "success", "asset_id": asset.asset_id, "vector_count": count}
    except Exception as e:
        log_message("ERROR", f"CRITICAL ERROR for {asset.asset_id}: {str(e)}")
        import traceback
        log_message("DEBUG", traceback.format_exc()) # 打印堆栈到日志文件
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            asset_data = json.loads(sys.argv[1])
            asset_obj = AcademicAsset.from_dict(asset_data)
            print(json.dumps(run_clip_work(asset_obj)))
        except Exception as e:
            log_message("ERROR", f"Entry point error: {e}")
            print(json.dumps({"status": "error", "message": str(e)}))