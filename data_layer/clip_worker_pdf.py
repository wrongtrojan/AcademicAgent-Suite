import os
import sys  # 补上缺失的导入
import json
import yaml
import torch
import logging
import numpy as np
from PIL import Image
import transformers
from transformers import CLIPProcessor, CLIPModel
from pathlib import Path

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CLIPWorker")
transformers.utils.logging.set_verbosity_error()

class CLIPWorker:
    def __init__(self, force_reprocess=False):
        # 1. 修正路径逻辑
        self.current_file_path = Path(__file__).resolve()
        # 脚本在 AcademicAgent-Suite/data_layer/，向上跳2级到达根目录
        self.project_root = self.current_file_path.parent.parent
        
        config_path = self.project_root / "configs" / "model_config.yaml"
        
        if not config_path.exists():
            logger.error(f"找不到配置文件: {config_path}")
            sys.exit(1)

        with open(config_path, 'r', encoding='utf-8') as f:
            self.full_config = yaml.safe_load(f)
        
        # 从配置中读取路径
        self.model_path = self.full_config['model_paths']['clip']
        self.processed_root = os.path.join(self.full_config['paths']['processed_storage'], "magic-pdf")
        
        self.force_reprocess = force_reprocess
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self._model = None
        self._processor = None

    @property
    def model(self):
        if self._model is None:
            logger.info(f"--- 开启离线模式，加载 CLIP 权重: {self.model_path} ---")
            # 确保使用本地路径加载
            self._model = CLIPModel.from_pretrained(self.model_path, local_files_only=True).to(self.device)
            self._model.eval()
        return self._model

    @property
    def processor(self):
        if self._processor is None:
            self._processor = CLIPProcessor.from_pretrained(self.model_path, local_files_only=True)
        return self._processor

    def _get_aligned_embedding(self, outputs):
        """保持原有的强健解包逻辑"""
        tensor = None
        if hasattr(outputs, "image_embeds"):
            tensor = outputs.image_embeds
        elif hasattr(outputs, "text_embeds"):
            tensor = outputs.text_embeds
        elif hasattr(outputs, "pooler_output"):
            tensor = outputs.pooler_output
            
        if tensor is None:
            if isinstance(outputs, (list, tuple)):
                tensor = outputs[0]
            elif isinstance(outputs, dict):
                tensor = list(outputs.values())[0]
            elif hasattr(outputs, "last_hidden_state"):
                tensor = outputs.last_hidden_state.mean(dim=1)
            else:
                try:
                    tensor = outputs[0]
                except:
                    tensor = outputs

        if hasattr(tensor, "detach"):
            return tensor.detach().cpu().numpy().flatten().tolist()
        else:
            return np.array(tensor).flatten().tolist()

    def batch_process(self):
        if not os.path.exists(self.processed_root):
            logger.error(f"路径不存在: {self.processed_root}")
            return

        for doc_name in os.listdir(self.processed_root):
            doc_path = os.path.join(self.processed_root, doc_name)
            if not os.path.isdir(doc_path): continue

            output_json = os.path.join(doc_path, "multimodal_features.json")
            
            # --- 增强的增量提示逻辑 ---
            if os.path.exists(output_json) and not self.force_reprocess:
                # 使用特殊的标记 [SKIP]，让你在大量日志中一眼看到
                logger.info(f"==== [SKIP] 已存在特征文件，跳过处理: {doc_name} ====")
                continue

            logger.info(f">>> [PROCESS] 正在处理新文档: {doc_name}")
            
            # 尝试不同的子目录结构
            found_ocr = False
            for sub in ["auto", "ocr"]:
                ocr_dir = os.path.join(doc_path, sub)
                if os.path.exists(ocr_dir):
                    found_ocr = True
                    break
            
            if not found_ocr:
                logger.warning(f"在 {doc_name} 中找不到 auto 或 ocr 目录，跳过")
                continue
                
            img_dir = os.path.join(ocr_dir, "images")
            content_list_path = os.path.join(ocr_dir, f"{doc_name}_content_list.json")

            doc_results = {"images": {}, "text_chunks": []}

            # 1. 处理图片
            if os.path.exists(img_dir):
                images = [f for f in os.listdir(img_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                for img_name in images:
                    try:
                        image = Image.open(os.path.join(img_dir, img_name)).convert("RGB")
                        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
                        with torch.no_grad():
                            outputs = self.model.get_image_features(**inputs)
                            doc_results["images"][img_name] = self._get_aligned_embedding(outputs)
                    except Exception as e:
                        logger.warning(f"图片 {img_name} 向量化失败: {e}")

            # 2. 处理文本
            if os.path.exists(content_list_path):
                try:
                    with open(content_list_path, 'r', encoding='utf-8') as f:
                        content_data = json.load(f)
                    for item in content_data:
                        text = item.get("text") or item.get("text_content") or ""
                        if len(text.strip()) < 5: continue 

                        inputs = self.processor(text=[text], return_tensors="pt", padding=True, truncation=True).to(self.device)
                        with torch.no_grad():
                            outputs = self.model.get_text_features(**inputs)
                            embedding = self._get_aligned_embedding(outputs)
                        
                        doc_results["text_chunks"].append({
                            "type": item.get("type", "text"),
                            "text_slice": text[:50], 
                            "embedding": embedding
                        })
                except Exception as e:
                    logger.warning(f"文本块处理失败: {e}")

            # 3. 保存结果
            with open(output_json, "w", encoding='utf-8') as f:
                json.dump(doc_results, f, indent=4, ensure_ascii=False)
            logger.info(f"文档 {doc_name} 特征保存成功")

if __name__ == "__main__":
    worker = CLIPWorker(force_reprocess=False)
    worker.batch_process()