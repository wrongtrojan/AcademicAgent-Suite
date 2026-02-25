import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

# Import our custom orchestrator and routes
from web.orchestrator import orchestrator_instance, AgentLogicOrchestrator
from web.api.v1.ingestion import router as ingestion_router
from web.api.v1.chat import router as chat_router
from web.api.v1.assets import router as assets_router

# Standardized logging for the Web Entry Point
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [WEB-MAIN] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WebMain")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles the startup and shutdown of the Core Orchestrator.
    This ensures heavy models and tools are initialized only once.
    """
    logger.info("--- [System Startup] ---")
    # Initialize the singleton instance of our Brain
    orchestrator_instance["core"] = AgentLogicOrchestrator()
    
    yield
    
    logger.info("--- [System Shutdown] ---")
    orchestrator_instance.clear()

# Initialize FastAPI with lifespan management
app = FastAPI(
    title="AcademicAgent-Suite API",
    description="Backend API for multi-modal academic asset processing and reasoning.",
    version="1.0.0",
    lifespan=lifespan
)

# Standard CORS middleware to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Set to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Mount Static Files
# This allows the frontend to access summary_outline.json, frames, and docs directly.
# Accessible via: http://localhost:8000/processed/video/xxx/summary_outline.json
app.mount("/raw", StaticFiles(directory="storage/raw_files"), name="raw")
app.mount("/processed", StaticFiles(directory="storage/processed"), name="processed")

# 2. Include Routers
# We start with the ingestion router for Phase 1.
app.include_router(ingestion_router, prefix="/api/v1/ingest", tags=["Ingestion"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(assets_router, prefix="/api/v1/assets", tags=["Assets"])

@app.get("/")
async def root():
    return {"message": "AcademicAgent-Suite API is online.", "docs": "/docs"}