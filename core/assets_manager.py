import json
import logging
import asyncio
from enum import Enum
from pathlib import Path
from typing import Dict,Optional
from datetime import datetime

# --- 配置与日志 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [AssetSystem] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AssetManager")

class AssetStatus(Enum):
    UPLOADING = "Uploading"     # 接口已调用，文件正在写入磁盘
    RAW = "Raw"                 # 文件写入完成，进入待处理队列
    RECOGNIZING= "recognizing"  # 处理过程中
    CLIPING = "Cliping"
    STRUCTURING = "Structuring"
    INGESTING ="Ingesting"
    READY = "Ready"             # 处理完成
    FAILED = "Failed"           # 发生错误

class GlobalStatus(Enum):
    WAITING = "Waiting"     # 队列为空或未启动
    HANDLING = "Handling"   # 正在处理资产
    UPLOADING = "Uploading" # 有资产正在上传

class AssetType(Enum):
    PDF = "pdf"
    VIDEO = "video"

class AcademicAsset:
    """资产实例类：用于与 ServicesManager 交互"""
    def __init__(self, asset_id: str, asset_type: AssetType, asset_raw_path: str):
        self.asset_id = asset_id
        self.asset_type = asset_type
        self.status = AssetStatus.UPLOADING 
        self.asset_raw_path = asset_raw_path
        self.asset_processed_path = ""
        self.created_at = datetime.now().isoformat()
        self.retry_count = 0

    def to_dict(self):
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type.value,
            "status": self.status.value,
            "asset_raw_path": self.asset_raw_path,
            "asset_processed_path": self.asset_processed_path,
            "created_at": self.created_at,
            "retry_count": self.retry_count
        }

    @classmethod
    def from_dict(cls, data: dict):
        # 统一使用带有 asset_ 前缀的键名
        asset = cls(
            asset_id=data["asset_id"], 
            asset_type=AssetType(data["asset_type"]), 
            asset_raw_path=data["asset_raw_path"]
        )
        asset.status = AssetStatus(data["status"])
        asset.asset_processed_path = data.get("asset_processed_path", "")
        asset.created_at = data.get("created_at")
        asset.retry_count = data.get("retry_count", 0)
        return asset

# --- 资产管理类 ---
class GlobalAssetManager:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GlobalAssetManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, storage_root: str = "./storage"):
        if hasattr(self, "_initialized"): return
        self.storage_root = Path(storage_root)
        self.db_file = self.storage_root / "assets_registry.json"
        
        self.assets_map: Dict[str, dict] = {}
        self.pending_queue = asyncio.Queue() 
        self.current_processing_id: Optional[str] = None
        self.is_worker_running = False
        self._worker_task = None  
        
        self._initialized = True
        self.load_state()

    async def register_new_upload(self, asset_id: str, asset_type: str, raw_path: str):
        """[API] 注册新上传 - 修正了字典键名"""
        async with self._lock:
            # 这里的键名必须与 AcademicAsset.to_dict() 保持一致
            self.assets_map[asset_id] = {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "status": AssetStatus.UPLOADING.value,
                "asset_raw_path": raw_path,
                "asset_processed_path": "",
                "created_at": datetime.now().isoformat(),
                "retry_count": 0
            }
            self.save_state()
            logger.info(f"Asset {asset_id} registered.")

    async def update_to_raw(self, asset_id: str):
        async with self._lock:
            if asset_id in self.assets_map:
                self.assets_map[asset_id]["status"] = AssetStatus.RAW.value
                self.save_state()
                logger.info(f"Asset {asset_id} moved to RAW and queued.")

    async def start_queue_processing(self):
        count = 0
        for aid, a_data in self.assets_map.items():
            if a_data["status"] == AssetStatus.RAW.value:
                # 检查是否已经在队列中（避免重复触发）
                await self.pending_queue.put(aid)
                count += 1
        if not self.is_worker_running:
            logger.info("Starting Asset Queue Worker...")
            self.is_worker_running = True
            self._worker_task = asyncio.create_task(self._queue_worker())
            self._worker_task.add_done_callback(self._on_worker_done)
            return {"status": "success", "message": f"Processor started. {count} assets queued."}
        return {"status": "success", "message": f"Worker already running. {count} new assets added to queue."}

    def _on_worker_done(self, task):
        self.is_worker_running = False
        try:
            task.result()
        except Exception as e:
            logger.error(f"Worker Task exited with CRITICAL ERROR: {e}", exc_info=True)
    
    def get_asset_status(self, asset_id: str) -> Optional[dict]:
        return self.assets_map.get(asset_id)

    def get_all_assets(self) -> Dict[str, dict]:
        return self.assets_map
    
    def get_global_status(self) -> dict:
        has_uploading = any(a["status"] == AssetStatus.UPLOADING.value for a in self.assets_map.values())
        state = GlobalStatus.WAITING.value
        if self.current_processing_id:
            state = GlobalStatus.HANDLING.value
        elif has_uploading:
            state = GlobalStatus.UPLOADING.value

        return {
            "global_state": state,
            "assets_number": len(self.assets_map),
            "queue_length": self.pending_queue.qsize(),
            "current_processing": self.current_processing_id
        }

    async def _queue_worker(self):
        logger.info("Worker: [ENTERED] Background loop started.")
        try:
            from core.services_manager import ServicesManager
            sm = ServicesManager()
            logger.info("Worker: ServicesManager integrated.")
        except Exception as e:
            logger.error(f"Worker: Failed to import ServicesManager: {e}")
            return

        while True:
            try:
                q_size = self.pending_queue.qsize()
                logger.info(f"Worker: Waiting for task... Current Queue Size: {q_size}")
                
                asset_id = await self.pending_queue.get()
                self.current_processing_id = asset_id
                
                logger.info(f"Worker: >>> START Processing: {asset_id}")
                await self._drive_pipeline(asset_id, sm)
                logger.info(f"Worker: <<< FINISH Processing: {asset_id}")

            except Exception as e:
                logger.error(f"Worker: Pipeline Error for {self.current_processing_id}: {e}", exc_info=True)
            finally:
                if self.current_processing_id:
                    self.current_processing_id = None
                    self.pending_queue.task_done()
                self.save_state()

    async def _drive_pipeline(self, asset_id: str, sm):
        """驱动状态机：Raw -> Ready"""
        # 每次从 map 获取最新的字典数据
        asset_dict = self.assets_map[asset_id]
        
        steps = [
            (AssetStatus.RAW, AssetStatus.RECOGNIZING),
            (AssetStatus.RECOGNIZING, AssetStatus.CLIPING),
            (AssetStatus.CLIPING, AssetStatus.STRUCTURING),
            (AssetStatus.STRUCTURING, AssetStatus.INGESTING),
            (AssetStatus.INGESTING, AssetStatus.READY)
        ]

        for current_step, next_step in steps:
            asset_dict["status"] = next_step.value
            self.save_state()

            res = {"status": "error", "message": "Unknown step"}
            
            # 关键：实例化 AcademicAsset 对象传递给服务
            asset_obj = AcademicAsset.from_dict(asset_dict)
            
            if current_step == AssetStatus.RAW:
                if asset_dict["asset_type"] == "pdf":
                    res = await sm.start_pdf_recognition(asset_obj)
                else:
                    res = await sm.start_video_recognition(asset_obj)
            
            elif current_step == AssetStatus.RECOGNIZING:
                res = await sm.start_clip_indexing(asset_obj)
            
            elif current_step == AssetStatus.CLIPING:
                res = await sm.start_structure_generation(asset_obj)
            
            elif current_step == AssetStatus.STRUCTURING:
                res = await sm.start_milvus_ingestion(asset_obj)
            
            elif current_step == AssetStatus.INGESTING:
                res = {"status": "success"}

            if res.get("status") == "success":
                path_val = res.get("processed_path")
                if path_val:
                    if not str(path_val).startswith("/"):
                        full_path = (self.storage_root / "processed" / path_val).resolve()
                        asset_dict["asset_processed_path"] = str(full_path)
                    else:
                        asset_dict["asset_processed_path"] = str(path_val)
                
                if next_step == AssetStatus.READY:
                    asset_dict["status"] = AssetStatus.READY.value
            else:
                asset_dict["status"] = AssetStatus.FAILED.value
                logger.error(f"Pipeline failed at {current_step.value}: {res.get('message')}")
                break 

    def save_state(self):
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.assets_map, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Save state failed: {e}")

    def load_state(self):
        if self.db_file.exists():
            try:
                data = json.loads(self.db_file.read_text(encoding='utf-8'))
                # 兼容旧版本 JSON 结构或直接覆盖
                if "assets_map" in data:
                    self.assets_map = data["assets_map"]
                else:
                    self.assets_map = data
            
            except Exception as e:
                logger.error(f"Load state failed: {e}")