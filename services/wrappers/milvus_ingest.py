import os
import sys
import json
import yaml
import traceback
from pathlib import Path
from datetime import datetime
from minio import Minio
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

# 注入项目根目录以加载 core 模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from core.assets_manager import AcademicAsset, AssetType

# --- 基础日志函数 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file_path = LOG_DIR / "milvus_ingest.log"

def log_message(level, msg):
    """最基础的日志重定向：同时打印到控制台并追加到文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    formatted_msg = f"{timestamp} - [MilvusIngest] - {level} - {msg}"
    
    # 输出到控制台
    print(formatted_msg)
    
    # 追加到文件
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(formatted_msg + "\n")

class MilvusIngestor:
    def __init__(self, global_cfg_path="configs/model_config.yaml", milvus_cfg_path="configs/milvus_config.yaml"):
        self.project_root = PROJECT_ROOT
        with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
            self.model_cfg = yaml.safe_load(f)
        with open(self.project_root / milvus_cfg_path, 'r', encoding='utf-8') as f:
            self.db_cfg = yaml.safe_load(f)

        self.minio_client = Minio(
            "localhost:9000",
            access_key="minioadmin",  
            secret_key="minioadmin",
            secure=False
        )
        self.bucket_name = "academic-assets"
        self._setup_minio()
        self._setup_milvus()

    def _setup_minio(self):
        if not self.minio_client.bucket_exists(self.bucket_name):
            self.minio_client.make_bucket(self.bucket_name)
            policy = {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetBucketLocation", "s3:ListBucket", "s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{self.bucket_name}", f"arn:aws:s3:::{self.bucket_name}/*"]
                }]
            }
            self.minio_client.set_bucket_policy(self.bucket_name, json.dumps(policy))
            log_message("INFO", f"MinIO Bucket {self.bucket_name} initialized")

    def _setup_milvus(self):
        conn = self.db_cfg['connection']
        connections.connect("default", host=conn['host'], port=conn['port'])
        
        c = self.db_cfg['collection']
        s = self.db_cfg['schema']
        
        if not utility.has_collection(c['name']):
            fields = [
                FieldSchema(name=s['pk'], dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="asset_name", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="modality", dtype=DataType.VARCHAR, max_length=50),      
                FieldSchema(name="content_type", dtype=DataType.VARCHAR, max_length=50),  
                FieldSchema(name="content_ref", dtype=DataType.VARCHAR, max_length=1000), 
                FieldSchema(name="timestamp", dtype=DataType.DOUBLE),               
                FieldSchema(name="coordinates", dtype=DataType.VARCHAR, max_length=500),    
                FieldSchema(name=s['vec'], dtype=DataType.FLOAT_VECTOR, dim=c['dim'])
            ]
            schema = CollectionSchema(fields, "Unified Academic Assets with MinIO URLs")
            self.collection = Collection(c['name'], schema)
            index_params = {"metric_type": c['metric_type'], "index_type": c['index_type'], "params": {"nlist": c['nlist']}}
            self.collection.create_index(field_name=s['vec'], index_params=index_params)
        else:
            self.collection = Collection(c['name'])
        
        self.collection.load()
        log_message("INFO", f"Milvus Collection {c['name']} loaded")

    def _upload_file(self, local_path, remote_path):
        p = Path(local_path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        try:
            self.minio_client.fput_object(self.bucket_name, remote_path, str(p))
            return f"http://127.0.0.1:9000/{self.bucket_name}/{remote_path}" 
        except Exception as e:
            log_message("ERROR", f"MinIO upload fail: {e}")
            return None

    def ingest_asset(self, asset: AcademicAsset):
        log_message("INFO", f"Processing Asset: {asset.asset_id} ({asset.asset_type.value})")
        
        if asset.asset_type == AssetType.PDF:
            data = self._process_pdf(asset)
        elif asset.asset_type == AssetType.VIDEO:
            data = self._process_video(asset)
        else:
            return {"status": "error", "message": "unsupported type"}

        if data and data[0]:
            self.collection.insert(data)
            self.collection.flush()
            log_message("INFO", f"DONE: {asset.asset_id} ingestion complete, {len(data[0])} records.")
            return len(data[0])
        return 0

    def _process_pdf(self, asset: AcademicAsset):
        clean_id = asset.asset_id.replace(".pdf", "")
        doc_dir = Path(self.model_cfg['paths']['processed_storage']) / "magic-pdf" / clean_id
        feature_path = doc_dir / "clip_features.json"
        
        if not feature_path.exists():
            log_message("ERROR", f"Feature file missing: {feature_path}")
            return None

        with open(feature_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        img_dir = None
        for sub in ["auto", "ocr"]:
            if (doc_dir / sub / "images").exists():
                img_dir = doc_dir / sub / "images"
                break

        names, modalities, types, refs, timestamps, coords, vecs = [], [], [], [], [], [], []

        for img_name, img_info in data.get("images", {}).items():
            actual_vec = img_info.get("embedding") or img_info.get("img_vector")
            if not actual_vec: continue

            remote_url = img_name
            if img_dir:
                remote_url = self._upload_file(img_dir / img_name, f"pdf/{clean_id}/{img_name}")
            
            names.append(asset.asset_id)
            modalities.append("pdf")
            types.append("image")
            refs.append(remote_url if remote_url else img_name)
            timestamps.append(float(img_info.get("page_idx", 0) + 1))
            coords.append(json.dumps(img_info.get("bbox", [])))
            vecs.append(actual_vec)

        for chunk in data.get("text_chunks", []):
            actual_vec = chunk.get("embedding") or chunk.get("text_vector")
            if not actual_vec: continue

            names.append(asset.asset_id)
            modalities.append("pdf")
            types.append("text")
            refs.append(chunk.get("text_slice", "")[:1000])
            vecs.append(actual_vec)
            timestamps.append(float(chunk.get("page_idx", 0) + 1))
            coords.append(json.dumps(chunk.get("bbox", [])))

        return [names, modalities, types, refs, timestamps, coords, vecs]

    def _process_video(self, asset: AcademicAsset):
        v_dir = Path(self.model_cfg['paths']['processed_storage']) / "video" / asset.asset_id
        feature_path = v_dir / "clip_features.json"
        frames_dir = v_dir / "frames"

        if not feature_path.exists():
            log_message("ERROR", f"Feature file missing: {feature_path}")
            return None

        with open(feature_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        names, modalities, types, refs, timestamps, vecs = [], [], [], [], [], []
        alignments = data.get("alignments", []) if isinstance(data, dict) else data

        for item in alignments:
            if item.get("img_vector"):
                img_path = frames_dir / item['frame_name']
                remote_url = self._upload_file(img_path, f"video/{asset.asset_id}/{item['frame_name']}")
                
                names.append(asset.asset_id)
                modalities.append("video")
                types.append("image_frame")
                refs.append(remote_url if remote_url else item['frame_name'])
                timestamps.append(item['timestamp'])
                vecs.append(item['img_vector'])

            if item.get("text_vector"):
                names.append(asset.asset_id)
                modalities.append("video")
                types.append("transcript_context")
                refs.append(item['content'][:500])
                timestamps.append(item['timestamp'])
                vecs.append(item['text_vector'])

        coords = ["null"] * len(names)
        return [names, modalities, types, refs, timestamps, coords, vecs]

def run_milvus_ingest(asset: AcademicAsset):
    log_message("INFO", f"--- Ingest Start: {datetime.now()} ---")
    try:
        ingestor = MilvusIngestor()
        count = ingestor.ingest_asset(asset)
        return {"status": "success", "asset_id": asset.asset_id, "vector_inserted": count}
    except Exception as e:
        log_message("ERROR", f"Ingest Error: {str(e)}")
        log_message("DEBUG", traceback.format_exc())
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            asset_data = json.loads(sys.argv[1])
            asset_obj = AcademicAsset.from_dict(asset_data)
            print(json.dumps(run_milvus_ingest(asset_obj)))
        except Exception as e:
            log_message("ERROR", f"Entry point error: {e}")
            print(json.dumps({"status": "error", "message": str(e)}))