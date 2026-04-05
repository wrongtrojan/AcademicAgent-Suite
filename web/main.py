import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

# 导入业务逻辑单例
from core.assets_manager import GlobalAssetManager


# 导入新编写的 API 路由 (假设文件路径如下)
from web.api.v1.upload import router as upload_router
from web.api.v1.assets import router as assets_router
from web.api.v1.status import router as status_router
from web.api.v1.chats import router as chats_router

# 标准化日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [WEB-MAIN] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WebMain")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    处理系统的启动与关闭逻辑。
    """
    logger.info("--- [System Startup] ---")
    
    # 确保存储目录存在
    Path("./storage/raw/pdf").mkdir(parents=True, exist_ok=True)
    Path("./storage/raw/video").mkdir(parents=True, exist_ok=True)
    Path("./storage/processed").mkdir(parents=True, exist_ok=True)

    # 初始化单例管理器
    # 初始化后会从 json 自动加载历史状态并把 RAW 资产重新入队
    asset_manager = GlobalAssetManager()

    
    yield
    
    logger.info("--- [System Shutdown] ---")

# 初始化 FastAPI
app = FastAPI(
    title="ContextMap API",
    description="后端 API：支持多模态资产处理、状态机管理及推理。",
    version="1.1.0",
    lifespan=lifespan
)

# CORS 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. 挂载静态文件访问
# 前端通过 http://localhost:8000/raw/pdf/xxx.pdf 进行预览
app.mount("/raw", StaticFiles(directory="storage/raw"), name="raw")
app.mount("/processed", StaticFiles(directory="storage/processed"), name="processed")

# 2. 注册 v1 版本路由
# 资产上传流转 API
app.include_router(upload_router, prefix="/api/v1/upload", tags=["Upload"])
# 资产操作与同步 API
app.include_router(assets_router, prefix="/api/v1/assets", tags=["Assets"])
# 状态监控 API
app.include_router(status_router, prefix="/api/v1/status", tags=["Status"])
# # 聊天推理 API
app.include_router(chats_router, prefix="/api/v1/chats", tags=["Chats"])

@app.get("/")
async def root():
    return {
        "message": "AcademicAgent-Suite API is online.",
        "api_v1": "/api/v1",
        "docs": "/docs"
    }
    