import logging
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from core.assets_manager import GlobalAssetManager, AssetStatus

logger = logging.getLogger("AssetsAPI")
router = APIRouter()
manager = GlobalAssetManager()

@router.post("/sync")
async def trigger_sync():
    """
    [API] 申请处理资产：唤醒后台 Worker 消费队列
    """
    res = await manager.start_queue_processing()
    return res

@router.get("/structure")
async def get_structure(asset_id: str):
    """
    [API] 获取结构化大纲 - 直接读取并返回 summary_outline.json 内容
    """
    asset = manager.get_asset_status(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # 只有当状态为 READY 时，处理后的文件才保证存在
    if asset["status"] != AssetStatus.READY.value:
        return {
            "status": "processing", 
            "current_step": asset["status"],
            "message": "Structure is not generated yet."
        }

    # 1. 构造文件完整路径
    if asset["asset_type"]=="pdf":
        asset["asset_processed_path"] = asset["asset_processed_path"].replace(".pdf","")
    processed_dir = Path(asset["asset_processed_path"])
    outline_file = processed_dir / "summary_outline.json"

    # 2. 检查文件物理是否存在
    if not outline_file.exists():
        logger.error(f"File missing: {outline_file}")
        raise HTTPException(
            status_code=500, 
            detail="Structure file missing on server despite READY status"
        )

    # 3. 读取并解析 JSON 文件
    try:
        with open(outline_file, 'r', encoding='utf-8') as f:
            outline_data = json.load(f)
            
        return {
            "status": "success",
            "data": outline_data,  # 直接返回解析后的 JSON 结构
            "message": "Outline retrieved successfully"
        }
    except Exception as e:
        logger.error(f"Failed to read outline file for {asset_id}: {e}")
        raise HTTPException(status_code=500, detail="Error reading structure data")

@router.get("/preview")
async def get_preview(asset_id: str):
    """
    [API] 申请预览资产的处理后路径
    """
    asset = manager.get_asset_status(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    result_path = asset["asset_raw_path"].replace("storage","")
    return {
        "asset_id": asset_id,
        "raw_path": result_path,
        "type": asset["asset_type"]
    }