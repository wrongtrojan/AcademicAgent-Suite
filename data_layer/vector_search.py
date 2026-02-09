import torch
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any
from pymilvus import connections, Collection
from transformers import CLIPProcessor, CLIPModel

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
        logger.info("🚀 Searcher initialized and Milvus collection loaded.")

    def _encode_query(self, query: str) -> List[float]:
        inputs = self.processor(text=[query], return_tensors="pt", padding=True, truncation=True).to(self.device)
        with torch.no_grad():
            text_features = self.model.get_text_features(**inputs)
            if hasattr(text_features, "pooler_output"):
                text_features = text_features.pooler_output
            text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
            return text_features.cpu().numpy()[0].tolist()

    def search(self, query: str, asset_id: str = None, top_k: int = 10) -> List[Dict[str, Any]]:
        query_vector = self._encode_query(query)
        
        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        expr = f'asset_name == "{asset_id}"' if asset_id else None

        results = self.collection.search(
            data=[query_vector],
            anns_field="vector", 
            param=search_params,
            limit=top_k * 2,  
            expr=expr,
            output_fields=["asset_name", "modality", "content_type", "content_ref", "timestamp"]
        )

        formatted_results = []
        query_lower = query.lower()

        for hit in results[0]:
            content = hit.entity.get("content_ref") or ""
            score = hit.score
            modality = hit.entity.get("modality")

            if query_lower in content.lower():
                
                score += 0.15 
            
            if modality == "video":
                score += 0.02

            formatted_results.append({
                "score": score,
                "asset": hit.entity.get("asset_name"),
                "modality": modality,
                "content_type": hit.entity.get("content_type"),
                "content": content, 
                "timestamp": hit.entity.get("timestamp")
            })

        formatted_results = sorted(formatted_results, key=lambda x: x['score'], reverse=True)

        return formatted_results[:top_k]

if __name__ == "__main__":
    searcher = AcademicSearcher()
    res = searcher.search("DDL", top_k=10)
    for r in res:
        print(f"[{r['modality']}] Score: {r['score']:.4f} | Content: {r['content'][:50]}...")