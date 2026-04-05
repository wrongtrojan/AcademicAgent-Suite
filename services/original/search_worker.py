import torch
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pymilvus import connections, Collection
from transformers import CLIPProcessor, CLIPModel

# Standardized English logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Worker] - %(levelname)s - %(message)s')
logger = logging.getLogger("SearchWorker")

class AcademicSearchWorker:
    def __init__(self, config_path="configs/model_config.yaml", milvus_config="configs/milvus_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        
        with open(self.project_root / config_path, 'r', encoding='utf-8') as f:
            self.model_cfg = yaml.safe_load(f)
        with open(self.project_root / milvus_config, 'r', encoding='utf-8') as f:
            self.db_cfg = yaml.safe_load(f)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        model_path = self.model_cfg['model_paths']['clip']
        self.model = CLIPModel.from_pretrained(model_path).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_path)
        
        conn = self.db_cfg['connection']
        connections.connect("default", host=conn['host'], port=conn['port'])
        self.collection = Collection(self.db_cfg['collection']['name'])
        self.collection.load()
        logger.info("SearchWorker initialized: CLIP model and Milvus collection loaded.")

    def _encode_query(self, query: str) -> List[float]:
        inputs = self.processor(text=[query], return_tensors="pt", padding=True, truncation=True).to(self.device)
        with torch.no_grad():
            text_features = self.model.get_text_features(**inputs)
            if hasattr(text_features, "pooler_output"):
                text_features = text_features.pooler_output
            # L2 Normalization for IP (Inner Product) consistency
            text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
            return text_features.cpu().numpy()[0].tolist()

    def search(self, query: str, preferences: Optional[Dict] = None, top_k: int = 10) -> List[Dict[str, Any]]:
        query_vector = self._encode_query(query)
        search_params = {"metric_type": "IP", "params": {"nprobe": 12}}
        
        # Candidate expansion for soft-scoring (5x top_k)
        candidates = self.collection.search(
            data=[query_vector],
            anns_field="vector", 
            param=search_params,
            limit=top_k * 5,  
            output_fields=["asset_name", "modality", "content_type", "content_ref", "coordinates", "timestamp"]
        )

        formatted_results = []
        query_lower = query.lower()
        
        for hit in candidates[0]:
            base_score = float(hit.score)
            bonus = 0.0
            
            entity = hit.entity
            asset_name = entity.get("asset_name", "")
            modality = entity.get("modality", "")
            timestamp = entity.get("timestamp")
            content = entity.get("content_ref") or ""
            c_type = entity.get("content_type", "")

            if preferences:
                # 1. Asset Name Match (High Priority)
                pref_asset = preferences.get("asset_name")
                if pref_asset and pref_asset.lower() in asset_name.lower():
                    bonus += 0.40
                
                # 2. Modality Preference
                pref_mod = preferences.get("modality")
                if pref_mod and pref_mod == modality:
                    bonus += 0.20
                
                # 3. Precise Page/Timestamp Match
                # Note: For PDF, timestamp field stores the page number
                pref_time = preferences.get("timestamp")
                if pref_time is not None:
                    try:
                        if abs(float(timestamp) - float(pref_time)) < 0.01:
                            bonus += 0.45 # Strongest signal for specific page/time
                    except (TypeError, ValueError):
                        pass

            # 4. Content Heuristics
            if query_lower in content.lower(): 
                bonus += 0.15
            
            # 5. Type-specific boosts
            if modality == "video" and c_type == "transcript_context":
                bonus += 0.05
            elif modality == "pdf" and c_type in ["heading", "title"]:
                bonus += 0.10

            final_score = base_score + bonus

            formatted_results.append({
                "score": round(float(final_score), 4),
                "base_vector_score": round(base_score, 4),
                "content": content,
                "metadata": {
                    "asset_name": asset_name,
                    "modality": modality,
                    "type": c_type,
                    "bbox": entity.get("coordinates"),
                    "timestamp": float(timestamp) if modality == "video" else None,
                    "page_label": int(float(timestamp)) if modality == "pdf" else None
                }
            })

        # Re-sort based on boosted scores
        formatted_results = sorted(formatted_results, key=lambda x: x['score'], reverse=True)
        return formatted_results[:top_k]

if __name__ == "__main__":
    # Internal test logic
    worker = AcademicSearchWorker()