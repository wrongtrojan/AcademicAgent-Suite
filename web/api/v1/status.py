from fastapi import APIRouter, Query
from core.assets_manager import GlobalAssetManager
from core.chats_manager import ChatsManager  

router = APIRouter()
manager = GlobalAssetManager()
chats_manager = ChatsManager()

@router.get("/single_asset")
async def get_single_status(asset_id : str = Query(None, description="可选，指定查询某个资产")):
    """
    [API] 查询单一资产状态
    """
    if asset_id:
      detail = manager.get_asset_status(asset_id)
      return {"status": "success", "data": detail} if detail else {"status": "error", "message": "Not Found"}  
    return {"status": "success", "data": manager.get_all_assets()}

@router.get("/global_assets")
async def get_global_status():
    """
    [API] 查询全局资产统计与队列状态
    """
    # 获取 GlobalAssetManager 中的统计信息
    status_info = manager.get_global_status()
    return {
        "status": "success",
        "data": status_info
    }

@router.get("/single_chat")
async def get_single_chat_status(chat_id: str = Query(None, description="可选，指定查询某个会话")):
    """[API] 查看当前内存中活跃的推理任务"""
    if chat_id:
        detail = chats_manager.get_chat_details(chat_id)
        return {"status": "success", "data": detail} if detail else {"status": "error", "message": "Not Found"}
    
    # 默认返回所有会话的快照
    return {"status": "success", "data": chats_manager.get_all_chats()}

@router.get("/global_chats")
async def get_global_chat_status():
    """[API] 查询全局推理引擎状态 (是否有会话正在占用 VRAM)"""
    return {"status": "success", "data": chats_manager.get_overall_status()}