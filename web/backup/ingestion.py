import logging
import aiofiles
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException,UploadFile, File

# Import our orchestrator gateway
from web.orchestrator import get_orchestrator, AgentLogicOrchestrator
# Standardized logging for Ingestion API
logger = logging.getLogger("IngestionAPI")

router = APIRouter()

@router.post("/sync")
async def trigger_global_sync(
    background_tasks: BackgroundTasks, 
    core: AgentLogicOrchestrator = Depends(get_orchestrator)
):
    """
    Endpoint to trigger the global asset ingestion process.
    Uses BackgroundTasks to ensure the HTTP request returns immediately 
    while the GPU-heavy processing runs in the background.
    """
    # 1. Pre-check: Is the system already busy?
    task_id = "global_sync_task" 
    if not core.state_manager.acquire_ingestion_lock(task_id):
        logger.warning("Sync request REJECTED: System is busy.")
        raise HTTPException(
            status_code=409, 
            detail="System is currently busy."
        )

    # 2. Trigger the task in background
    logger.info("Sync request ACCEPTED: Launching background ingestion stream.")
    background_tasks.add_task(core.trigger_sync)
    
    return {
        "status": "accepted",
        "message": "Global synchronization started. Poll /status for progress."
    }

@router.get("/status")
async def get_task_status(
    core: AgentLogicOrchestrator = Depends(get_orchestrator)
):
    """
    Endpoint for the frontend to poll the real-time progress of the ingestion pipeline.
    Returns VRAM lock status, active assets, and granular component progress.
    """
    state = core.get_system_snapshot()
    return state

@router.post("/upload")
async def upload_academic_asset(
    file: UploadFile = File(...),
    core: AgentLogicOrchestrator = Depends(get_orchestrator)
):
    """
    Receives a file and stores it in the corresponding raw_files directory.
    This is the entry point for the frontend to introduce new assets.
    """
    filename = file.filename
    extension = filename.split(".")[-1].lower()
    
    try:
        # 1. Determine destination based on file extension
        if extension == "pdf":
            target_dir = Path("storage/raw_files/PDF")
        elif extension in ["mp4", "mkv", "mov"]:
            target_dir = Path("storage/raw_files/video")
        else:
            logger.warning(f"Unsupported file type attempted: {extension}")
            return {"status": "error", "message": f"Unsupported file type: {extension}"}

        # 2. Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)
        save_path = target_dir / filename
        
        # 3. Asynchronously write the file to disk in chunks to avoid blocking
        # Using aiofiles to ensure the event loop remains responsive
        async with aiofiles.open(save_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):  # 1MB chunks
                await out_file.write(content)

        logger.info(f"Successfully uploaded {filename} to {target_dir}")
        
        # 4. Return success immediately without touching the global system state
        return {
            "status": "success",
            "filename": filename,
            "path": str(save_path)
        }
        
    except Exception as e:
        logger.error(f"Failed to upload file [{filename}]: {str(e)}")
        return {"status": "error", "message": str(e)}
