import os
import json
import yaml
import logging
from pathlib import Path
from minio import Minio
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

# ================= 日志配置 =================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - [UnifiedIngestor] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MilvusIngestor")

class UnifiedIngestor:
    def __init__(self, force_reset=False):
        # 1. 路径与配置加载
        self.project_root = Path(__file__).resolve().parent.parent
        config_dir = self.project_root / "configs"
        
        with open(config_dir / "model_config.yaml", 'r', encoding='utf-8') as f:
            self.model_cfg = yaml.safe_load(f)
        with open(config_dir / "milvus_config.yaml", 'r', encoding='utf-8') as f:
            self.db_cfg = yaml.safe_load(f)

        # 2. 初始化 MinIO 客户端 (基于你的 docker ps 输出)
        # 注意：这里建议在 milvus_config.yaml 中增加 minio 配置，目前先硬编码确保能跑
        self.minio_client = Minio(
            "localhost:9000",
            access_key="minioadmin",  # 请确认你的 MinIO 账号密码
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
            logger.warning(f"⚠️ 已强制重置集合: {self.col_name}")

        self._setup_collection()

    def _setup_minio(self):
        """确保 MinIO Bucket 存在并设置公共只读权限"""
        if not self.minio_client.bucket_exists(self.bucket_name):
            self.minio_client.make_bucket(self.bucket_name)
            # 设置策略让 Attu 能够直接预览图片（匿名可读）
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
            logger.info(f"📦 MinIO Bucket '{self.bucket_name}' 已创建并配置权限")

    def _upload_file(self, local_path, remote_path):
        # 1. 转换路径对象
        p = Path(local_path)
        
        # 2. 存在性检查 (核心修复)
        if not p.exists():
            logger.error(f"❌ 文件不存在，跳过上传: {p}")
            return None # 返回 None，后续入库逻辑会自动忽略此条目

        # 3. 校验是否为文件而非目录
        if not p.is_file():
            logger.error(f"⚠️ 路径不是有效文件: {p}")
            return None

        # 4. 0 字节损坏检查
        if p.stat().st_size == 0:
            logger.warning(f"⚠️ 检测到 0 字节损坏文件，跳过: {p}")
            return None

        try:
            # 执行上传
            self.minio_client.fput_object(self.bucket_name, remote_path, str(p))
            
            # 针对你“本地看图”的需求：
            # 只要你做了 SSH 9000 端口转发，Attu 就能通过这个 URL 在浏览器里渲染图片
            return f"http://127.0.0.1:9000/{self.bucket_name}/{remote_path}" 
            
        except Exception as e:
            logger.error(f"🔥 MinIO 上传异常: {e}")
            return None

    def _setup_collection(self):
        """定义 Schema 并检查兼容性"""
        if utility.has_collection(self.col_name):
            col = Collection(self.col_name)
            # 检查 asset_name 字段是否存在，不存在则视为旧版
            if "asset_name" not in [f.name for f in col.schema.fields]:
                logger.warning("检测到旧版结构，正在重建...")
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
        """PDF 入库：同步上传图片到 MinIO"""
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

            # 找到图片目录 (ocr 或 auto)
            img_dir = None
            for sub in ["auto", "ocr"]:
                if (doc_dir / sub / "images").exists():
                    img_dir = doc_dir / sub / "images"
                    break

            names, modalities, types, refs, timestamps, vecs = [], [], [], [], [], []

            # 1. 处理图片：先上传 MinIO，再记下 URL
            for img_name, vec in data.get("images", {}).items():
                remote_url = img_name
                if img_dir:
                    remote_url = self._upload_file(img_dir / img_name, f"pdf/{doc_dir.name}/{img_name}")
                
                names.append(doc_dir.name); modalities.append("pdf")
                types.append("image"); refs.append(remote_url)
                timestamps.append(-1.0); vecs.append(vec)

            # 2. 处理文本块
            for chunk in data.get("text_chunks", []):
                names.append(doc_dir.name); modalities.append("pdf")
                types.append("text"); refs.append(chunk.get("text_slice", ""))
                timestamps.append(-1.0); vecs.append(chunk["embedding"])

            if names:
                self.collection.insert([names, modalities, types, refs, timestamps, vecs])
                logger.info(f"✅ [DONE] PDF {doc_dir.name} 入库完成 (含图片上传)")

    def ingest_video_data(self):
        """视频入库：同步上传关键帧到 MinIO"""
        video_root = Path(self.model_cfg['paths']['processed_storage']) / "video"
        if not video_root.exists(): return

        for v_dir in video_root.iterdir():
            if not v_dir.is_dir(): continue
            meta_path = v_dir / "alignment_metadata.json"
            
            # 增量检查
            if not meta_path.exists() or self._is_ingested(v_dir.name, "video"):
                logger.info(f"⏭️  [SKIP] Video: {v_dir.name}")
                continue

            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 准备六个对齐的列表
            names, modalities, types, refs, timestamps, vecs = [], [], [], [], [], []
            frames_dir = v_dir / "frames"

            for item in data.get("alignments", []):
                # --- 1. 处理图像帧 (需过 MinIO) ---
                img_path = frames_dir / item['frame_name']
                remote_url = self._upload_file(img_path, f"video/{v_dir.name}/{item['frame_name']}")
                
                # 只有上传成功且有向量时才入库
                if remote_url and item.get("img_vector"):
                    names.append(v_dir.name)
                    modalities.append("video")
                    types.append("image_frame")
                    refs.append(remote_url)
                    timestamps.append(item['timestamp'])
                    vecs.append(item['img_vector'])

                # --- 2. 处理关联文本 (直接入库) ---
                if item.get("text_vector"):
                    names.append(v_dir.name)
                    modalities.append("video")
                    types.append("transcript_context")
                    # 存入文本内容前 500 字作为参考
                    refs.append(item.get('context_text', '')[:500])
                    timestamps.append(item['timestamp'])
                    vecs.append(item['text_vector'])

            # 批量插入
            if names:
                self.collection.insert([names, modalities, types, refs, timestamps, vecs])
                logger.info(f"✅ [DONE] 视频 {v_dir.name} 入库完成 (共 {len(names)} 条向量记录)")

    def finish(self):
        self.collection.flush()
        logger.info("✨ 数据同步与 MinIO 映射圆满完成")

if __name__ == "__main__":
    # 第一次运行建议 force_reset=True 以应用包含 content_ref(URL) 的逻辑
    ingestor = UnifiedIngestor(force_reset=False)
    ingestor.ingest_pdf_data()
    ingestor.ingest_video_data()
    ingestor.finish()