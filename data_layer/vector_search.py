import torch
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any
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

    def search(self, query: str, asset_id: str = None, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Refined search logic: Combining your original architecture with 
        enhanced academic reranking and structured metadata.
        """
        # 1. Get query vector using your robust internal method
        query_vector = self._encode_query(query)
        
        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        expr = f'asset_name == "{asset_id}"' if asset_id else None

        # 2. Milvus Execution
        results = self.collection.search(
            data=[query_vector],
            anns_field="vector", 
            param=search_params,
            limit=top_k * 2,  # Over-fetch for reranking
            expr=expr,
            output_fields=["asset_name", "modality", "content_type", "content_ref", "timestamp"]
        )

        formatted_results = []
        query_lower = query.lower()

        for hit in results[0]:
            content = hit.entity.get("content_ref") or ""
            score = hit.score
            modality = hit.entity.get("modality")

            # 3. Enhanced Academic Reranking (Local Consensus)
            # Boost if exact keyword is found in the text slice
            if query_lower in content.lower():
                score += 0.15 
            
            # Prefer transcripts for textual queries to ensure citation accuracy
            if modality == "video" and hit.entity.get("content_type") == "transcript_context":
                score += 0.05

            formatted_results.append({
                "score": round(float(score), 4),
                "content": content,
                "metadata": {
                    "asset_id": hit.entity.get("asset_name"),
                    "modality": modality,
                    "type": hit.entity.get("content_type"),
                    "timestamp": hit.entity.get("timestamp") if modality == "video" else None,
                    "page_label": hit.entity.get("timestamp") if modality == "pdf" else None # PDF uses timestamp field for page
                }
            })

        # Final Sort and Slice
        formatted_results = sorted(formatted_results, key=lambda x: x['score'], reverse=True)
        return formatted_results[:top_k]
    
if __name__ == "__main__":
    searcher = AcademicSearcher()
    # Testing with query "DDL"
    res = searcher.search("DDL", top_k=10)
    
    for r in res:
        # Accessing nested metadata fields
        m = r['metadata']
        modality = m['modality']
        content = r['content'][:50].replace('\n', ' ')
        
        # Displaying with anchors
        anchor = f"Time: {m['timestamp']}" if modality == 'video' else f"Page: {m['page_label']}"
        
        print(f"[{modality.upper()}] Score: {r['score']:.4f} | {anchor} | Content: {content}...")