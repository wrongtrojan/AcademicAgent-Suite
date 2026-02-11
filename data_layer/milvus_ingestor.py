import os
import json
import yaml
import logging
from pathlib import Path
from minio import Minio
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [UnifiedIngestor] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MilvusIngestor")

class UnifiedIngestor:
    def __init__(self, force_reset=False):
        self.project_root = Path(__file__).resolve().parent.parent
        config_dir = self.project_root / "configs"
        
        with open(config_dir / "model_config.yaml", 'r', encoding='utf-8') as f:
            self.model_cfg = yaml.safe_load(f)
        with open(config_dir / "milvus_config.yaml", 'r', encoding='utf-8') as f:
            self.db_cfg = yaml.safe_load(f)

        self.minio_client = Minio(
            "localhost:9000",
            access_key="minioadmin",  
            secret_key="minioadmin",
            secure=False
        )
        self.bucket_name = "academic-assets"
        self._setup_minio()

        # 3. 连接 Milvus
        conn = self.db_cfg['connection']
        connections.connect("default", host=conn['host'], port=conn['port'])
        self.col_name = self.db_cfg['collection']['name']
        
        if force_reset and utility.has_collection(self.col_name):
            utility.drop_collection(self.col_name)
            logger.warning(f"⚠️ Forced reset of collection: {self.col_name}")

        self._setup_collection()

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
            logger.info(f"📦 MinIO Bucket '{self.bucket_name}' created and permissions configured")

    def _upload_file(self, local_path, remote_path):
        p = Path(local_path)
        
        if not p.exists():
            logger.error(f"❌ File does not exist, skipping upload: {p}")
            return None 

        if not p.is_file():
            logger.error(f"⚠️ Path is not a valid file: {p}")
            return None

        if p.stat().st_size == 0:
            logger.warning(f"⚠️ 0-byte corrupted file detected, skipping: {p}")
            return None

        try:
            self.minio_client.fput_object(self.bucket_name, remote_path, str(p))
            return f"http://127.0.0.1:9000/{self.bucket_name}/{remote_path}" 
            
        except Exception as e:
            logger.error(f"🔥 MinIO upload exception: {e}")
            return None

    def _setup_collection(self):
        if utility.has_collection(self.col_name):
            col = Collection(self.col_name)
            if "asset_name" not in [f.name for f in col.schema.fields]:
                logger.warning("Legacy structure detected; rebuilding...")
                utility.drop_collection(self.col_name)
            else:
                self.collection = col
                self.collection.load()
                return

        c = self.db_cfg['collection']
        s = self.db_cfg['schema']
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
        self.collection = Collection(self.col_name, schema)
        
        index_params = {"metric_type": c['metric_type'], "index_type": c['index_type'], "params": {"nlist": c['nlist']}}
        self.collection.create_index(field_name=s['vec'], index_params=index_params)
        self.collection.load()
        logger.info(f"✅ Unified Milvus Collection Loaded (with MinIO support)")

    def _is_ingested(self, asset_name, modality):
        expr = f'asset_name == "{asset_name}" and modality == "{modality}"'
        res = self.collection.query(expr=expr, output_fields=["id"], limit=1)
        return len(res) > 0

    def ingest_pdf_data(self):
        pdf_root = Path(self.model_cfg['paths']['processed_storage']) / "magic-pdf"
        if not pdf_root.exists(): return

        for doc_dir in pdf_root.iterdir():
            if not doc_dir.is_dir(): continue
            feature_path = doc_dir / "multimodal_features.json"
            if not feature_path.exists() or self._is_ingested(doc_dir.name, "pdf"):
                logger.info(f"⏭️  [SKIP] PDF: {doc_dir.name}")
                continue

            with open(feature_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            img_dir = None
            for sub in ["auto", "ocr"]:
                if (doc_dir / sub / "images").exists():
                    img_dir = doc_dir / sub / "images"
                    break

            names, modalities, types, refs, timestamps, coords, vecs = [], [], [], [], [], [], []

            for img_name, img_info in data.get("images", {}).items():
                remote_url = img_name
                actual_vec=img_info.get("embedding")
                page_idx = img_info.get("page_idx", -1)
                if img_dir:
                    remote_url = self._upload_file(img_dir / img_name, f"pdf/{doc_dir.name}/{img_name}")
                if actual_vec:
                    names.append(doc_dir.name); modalities.append("pdf")
                    types.append("image"); refs.append(remote_url)
                    timestamps.append(float(page_idx+1)); vecs.append(actual_vec)
                    coords.append(json.dumps(chunk.get("bbox", [])))

            for chunk in data.get("text_chunks", []):
                names.append(doc_dir.name); modalities.append("pdf")
                types.append("text"); refs.append(chunk.get("text_slice", ""))
                vecs.append(chunk["embedding"])
                page_num = float(chunk.get("page_idx", 0) + 1) 
                coords.append(json.dumps(chunk.get("bbox", [])))
                timestamps.append(page_num)
            if names:
                self.collection.insert([names, modalities, types, refs, timestamps, coords, vecs])
                logger.info(f"✅ [DONE] PDF {doc_dir.name} ingestion complete (including image uploads)")

    def ingest_video_data(self):
        video_root = Path(self.model_cfg['paths']['processed_storage']) / "video"
        if not video_root.exists(): return

        for v_dir in video_root.iterdir():
            if not v_dir.is_dir(): continue
            meta_path = v_dir / "alignment_metadata.json"

            if not meta_path.exists() or self._is_ingested(v_dir.name, "video"):
                logger.info(f"⏭️  [SKIP] Video: {v_dir.name}")
                continue

            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            names, modalities, types, refs, timestamps, vecs = [], [], [], [], [], [] 
            frames_dir = v_dir / "frames"

            for item in data.get("alignments", []):
                img_path = frames_dir / item['frame_name']
                remote_url = self._upload_file(img_path, f"video/{v_dir.name}/{item['frame_name']}")
                
                if remote_url and item.get("img_vector"):
                    names.append(v_dir.name)
                    modalities.append("video")
                    types.append("image_frame")
                    refs.append(remote_url)
                    timestamps.append(item['timestamp'])
                    vecs.append(item['img_vector'])

                if item.get("text_vector"):
                    names.append(v_dir.name)
                    modalities.append("video")
                    types.append("transcript_context")
                    refs.append(item.get('context_text', '')[:500])
                    timestamps.append(item['timestamp'])
                    vecs.append(item['text_vector'])
            coords=["null"] * len(names)
            if names:
                self.collection.insert([names, modalities, types, refs, timestamps, coords, vecs])
                logger.info(f"✅ [DONE] Video {v_dir.name} ingestion complete (Total {len(names)} vector records)")

    def finish(self):
        self.collection.flush()
        logger.info("✨ Data synchronization and MinIO mapping completed successfully")

if __name__ == "__main__":
    ingestor = UnifiedIngestor(force_reset=True)
    ingestor.ingest_pdf_data()
    ingestor.ingest_video_data()
    ingestor.finish()