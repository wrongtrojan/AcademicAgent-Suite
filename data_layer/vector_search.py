import torch
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pymilvus import connections, Collection
from transformers import CLIPProcessor, CLIPModel

# English logging as per our consensus
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Searcher] - %(levelname)s - %(message)s')
logger = logging.getLogger("VectorSearcher")

class AcademicSearcher:
    def __init__(self, config_path="configs/model_config.yaml", milvus_config="configs/milvus_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent
        
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
        logger.info("🚀 Searcher initialized. CLIP encoding & Milvus standby.")

    def _encode_query(self, query: str) -> List[float]:
        """
        Robust encoding logic aligned with your original script.
        Handles version variance and L2 normalization.
        """
        inputs = self.processor(text=[query], return_tensors="pt", padding=True, truncation=True).to(self.device)
        with torch.no_grad():
            text_features = self.model.get_text_features(**inputs)
            
            # Handle transformers version compatibility
            if hasattr(text_features, "pooler_output"):
                text_features = text_features.pooler_output
            
            # L2 Normalization - Essential for IP metric consistency
            text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
            
            # Convert to flat list of floats for Milvus serialization
            return text_features.cpu().numpy()[0].tolist()

    def search(self, query: str, preferences: Optional[Dict] = None, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Soft-scoring search: Retrieve broader candidates and apply weight boosts based on metadata.
        :param preferences: Dict containing boost targets (e.g., {'asset_name': 'math', 'target_page': 1})
        """
        query_vector = self._encode_query(query)
        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        
        # Broad retrieval without hard filters
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
            asset_name = entity.get("asset_name")
            modality = entity.get("modality")
            timestamp = entity.get("timestamp")
            content = entity.get("content_ref") or ""

            if preferences:
                # A. Sequential Match logic
                pref_asset = preferences.get("asset_name")
                if pref_asset and pref_asset.lower() in asset_name.lower():
                    bonus += 0.35  
                
                # B. 
                pref_mod = preferences.get("modality")
                if pref_mod and pref_mod == modality:
                    bonus += 0.15
                
                # C. Page/Timestamp
                pref_time = preferences.get("timestamp")
                if pref_time is not None:
                    try:
                        if abs(float(timestamp) - float(pref_time)) < 0.1:
                            bonus += 0.40  
                    except: pass

            # D.Academic heuristics
            if query_lower in content.lower(): 
                bonus += 0.10
            if modality == "video" and entity.get("content_type") == "transcript_context":
                bonus += 0.05

            final_score = base_score + bonus

            formatted_results.append({
                "score": round(float(final_score), 4),
                "base_vector_score": round(base_score, 4),
                "content": content,
                "metadata": {
                    "asset_name": hit.entity.get("asset_name"),
                    "modality": modality,
                    "type": hit.entity.get("content_type"),
                    "bbox": hit.entity.get("coordinates") ,
                    "timestamp": hit.entity.get("timestamp") if modality == "video" else None,
                    "page_label": hit.entity.get("timestamp") if modality == "pdf" else None # PDF uses timestamp field for page
                }
            })

        # Final Sort and Slice
        formatted_results = sorted(formatted_results, key=lambda x: x['score'], reverse=True)
        return formatted_results[:top_k]
    
if __name__ == "__main__":
    searcher = AcademicSearcher()
