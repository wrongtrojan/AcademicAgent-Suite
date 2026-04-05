import logging
import aiofiles
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from core.assets_manager import GlobalAssetManager, AssetType

logger = logging.getLogger("UploadAPI")
router = APIRouter()

# 获取资产管理单例
manager = GlobalAssetManager()

@router.post("/file")
async def upload_academic_asset(
    file: UploadFile = File(...),
):
    """
    [API] 综合上传接口：
    1. 自动生成 asset_id (文件名)
    2. 注册为 Uploading 状态
    3. 异步写入磁盘
    4. 写入完成后切换为 Raw 并触发入队
    """
    filename = file.filename
    extension = filename.split(".")[-1].lower()
    asset_id = filename  # 或者使用 UUID，这里沿用你的逻辑以文件名为 ID
    
    # 1. 确定路径与类别
    if extension == "pdf":
        asset_type = "pdf"
        target_dir = Path("storage/raw/pdf")
    elif extension in ["mp4", "mkv", "mov"]:
        asset_type = "video"
        target_dir = Path("storage/raw/video")
    else:
        logger.warning(f"Unsupported file type: {extension}")
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {extension}")

    target_dir.mkdir(parents=True, exist_ok=True)
    save_path = target_dir / filename

    try:
        # 2. 发送消息给 assets_manager：生成实例，状态设为 Uploading
        await manager.register_new_upload(
            asset_id=asset_id, 
            asset_type=asset_type, 
            raw_path=str(save_path)
        )

        # 3. 开始异步写入磁盘
        async with aiofiles.open(save_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):  # 1MB chunks
                await out_file.write(content)

        logger.info(f"File {filename} disk write complete.")

        # 4. 关键点：写入完成后通知 manager 切换状态为 Raw 并入队
        await manager.update_to_raw(asset_id)

        return {
            "status": "success",
            "asset_id": asset_id,
            "current_state": "Raw",
            "message": "File uploaded and added to processing queue."
        }
        
    except Exception as e:
        logger.error(f"Failed to process upload for [{filename}]: {str(e)}")
        # 如果中途失败，状态可以留在 Uploading 或标记为 Failed
        return {"status": "error", "message": str(e)}