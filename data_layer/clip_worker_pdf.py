import os
import sys  
import json
import yaml
import torch
import logging
import numpy as np
from PIL import Image
import transformers
import torch.nn.functional as F
from transformers import CLIPProcessor, CLIPModel
from pathlib import Path

import tqdm
class DisabledTqdm:
    def __init__(self, *args, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def __iter__(self): return self
    def __next__(self): raise StopIteration
    def __getattr__(self, name):
        return lambda *args, **kwargs: None

tqdm.tqdm = DisabledTqdm
try:
    import tqdm.auto
    tqdm.auto.tqdm = DisabledTqdm
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CLIPWorker")
transformers.utils.logging.set_verbosity_error()

class CLIPWorker:
    def __init__(self, force_reprocess=False):
        self.current_file_path = Path(__file__).resolve()
        self.project_root = self.current_file_path.parent.parent
        
        config_path = self.project_root / "configs" / "model_config.yaml"
        
        if not config_path.exists():
            logger.error(f"Cannot find configuration file: {config_path}")
            sys.exit(1)

        with open(config_path, 'r', encoding='utf-8') as f:
            self.full_config = yaml.safe_load(f)
        
        self.model_path = self.full_config['model_paths']['clip']
        self.processed_root = os.path.join(self.full_config['paths']['processed_storage'], "magic-pdf")
        
        self.force_reprocess = force_reprocess
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self._model = None
        self._processor = None

    @property
    def model(self):
        if self._model is None:
            logger.info(f"--- Offline mode enabled, loading CLIP weights: {self.model_path} ---")
            self._model = CLIPModel.from_pretrained(self.model_path, local_files_only=True).to(self.device)
            self._model.eval()
        return self._model

    @property
    def processor(self):
        if self._processor is None:
            self._processor = CLIPProcessor.from_pretrained(self.model_path, local_files_only=True)
        return self._processor

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

    def batch_process(self):
        if not os.path.exists(self.processed_root):
            logger.error(f"Path does not exist: {self.processed_root}")
            return

        for doc_name in os.listdir(self.processed_root):
            doc_path = os.path.join(self.processed_root, doc_name)
            if not os.path.isdir(doc_path): continue

            output_json = os.path.join(doc_path, "multimodal_features.json")

            if os.path.exists(output_json) and not self.force_reprocess:
                logger.info(f"==== [SKIP] Feature file already exists, skipping processing: {doc_name} ====")
                continue

            logger.info(f">>> [PROCESS] Processing new document: {doc_name}")
            
            found_ocr = False
            for sub in ["auto", "ocr"]:
                ocr_dir = os.path.join(doc_path, sub)
                if os.path.exists(ocr_dir):
                    found_ocr = True
                    break
            
            if not found_ocr:
                logger.warning(f"Could not find auto or ocr directory in {doc_name}, skipping")
                continue
                
            img_dir = os.path.join(ocr_dir, "images")
            content_list_path = os.path.join(ocr_dir, f"{doc_name}_content_list.json")

            doc_results = {"images": {}, "text_chunks": []}

            if os.path.exists(content_list_path):
                try:
                    with open(content_list_path, 'r', encoding='utf-8') as f:
                        content_data = json.load(f)
                    for item in content_data:
                        page_idx = item.get("page_idx", -1) 
                        item_type = item.get("type", "")
                        
                        if item_type in ["image", "table"] and "img_path" in item:
                            img_relative_dir = item["img_path"]
                            full_img_path = os.path.join(ocr_dir, img_relative_dir)

                            if os.path.exists(full_img_path):
                                try:
                                    image = Image.open(full_img_path).convert("RGB")
                                    inputs = self.processor(images=image, return_tensors="pt").to(self.device)
                                    with torch.no_grad():
                                        outputs = self.model.get_image_features(**inputs)
                                        embedding = self._get_aligned_embedding(outputs)
                                    
                                    img_name = os.path.basename(img_relative_dir)
                                    img_caption = item.get("img_caption", "")
                                    doc_results["images"][img_name] = {
                                        "type": item_type,
                                        "page_idx": page_idx,
                                        "text_slice": img_caption[:50],
                                        "embedding": embedding,
                                        
                                        
                                    }
                                except Exception as e:
                                    logger.warning(f"Image {img_name} failed: {e}")
                        
                        else:            
                            text = item.get("text") or item.get("text_content") or ""
                            if len(text.strip()) < 5: continue 

                            inputs = self.processor(text=[text], return_tensors="pt", padding=True, truncation=True).to(self.device)
                            with torch.no_grad():
                                outputs = self.model.get_text_features(**inputs)
                                embedding = self._get_aligned_embedding(outputs)
                            
                            doc_results["text_chunks"].append({
                                "type": item.get("type", "text"),
                                "page_idx": page_idx,
                                "text_slice": text[:50], 
                                "embedding": embedding
                            })
                except Exception as e:
                    logger.warning(f"Text chunk processing failed: {e}")

            # 3. 保存结果
            with open(output_json, "w", encoding='utf-8') as f:
                json.dump(doc_results, f, indent=4, ensure_ascii=False)
            logger.info(f"Document {doc_name} features saved successfully")

if __name__ == "__main__":
    worker = CLIPWorker(force_reprocess=False)
    worker.batch_process()