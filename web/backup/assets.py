import logging
from fastapi import APIRouter, Depends
from web.orchestrator import get_orchestrator, AgentLogicOrchestrator

logger = logging.getLogger("AssetsAPI")

router = APIRouter()

@router.get("/map")
async def get_asset_map(core: AgentLogicOrchestrator = Depends(get_orchestrator)):
    """
    Returns the hierarchical map of all processed academic assets.
    Used by the frontend sidebar to render the asset tree and outlines.
    """
    try:
        asset_map = core.get_assets_map()
        return {
            "status": "success",
            "data": asset_map
        }
    except Exception as e:
        logger.error(f"Failed to fetch asset map: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }