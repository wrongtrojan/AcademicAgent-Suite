"""FastAPI gateway: upload, asset sync, status, structure, preview, chats (SSE)."""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.asset_manager import AssetManager
from core.prompt_manager import PromptManager
from core.session_manager import SessionManager
from gateway.chat_graph import run_chat_turn
from gateway.http_logging_middleware import HttpRequestLoggingMiddleware
from gateway.outline_utils import outline_to_frontend
from shared.database.pool import get_database
from shared.logging_config import setup_logging

setup_logging("gateway")
logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "./storage")).resolve()

# OpenAPI /docs 分组（避免全部落在 default）
_OPENAPI_TAGS = [
    {"name": "system", "description": "系统与健康检查。"},
    {"name": "assets", "description": "资产上传与处理管线入队。"},
    {"name": "status_preview", "description": "资产/会话状态、预览与大纲。"},
    {"name": "chats", "description": "会话创建与 SSE 对话流。"},
    {"name": "experts_audit", "description": "专家登记与审计日志。"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("lifespan | startup | storage=%s", STORAGE_ROOT)
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    db = get_database()
    await db.connect()
    pm = PromptManager()
    await pm.ensure_seed_prompts()
    yield
    logger.info("lifespan | shutdown")
    await db.close()


app = FastAPI(
    title="ContextMap Gateway",
    lifespan=lifespan,
    openapi_tags=_OPENAPI_TAGS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Outermost: full request duration + request_id (add after CORS).
app.add_middleware(HttpRequestLoggingMiddleware)

if STORAGE_ROOT.exists():
    app.mount("/static/storage", StaticFiles(directory=str(STORAGE_ROOT)), name="storage")


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/upload/file", tags=["assets"])
async def upload_file(
    file: UploadFile = File(...),
    title: str | None = Query(None),
) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    ext = (file.filename or "asset.bin").rsplit(".", 1)[-1].lower()
    asset_type = "pdf" if ext == "pdf" else "video"
    am = AssetManager()
    await am.connect()
    try:
        asset_id, upload_url = await am.register_upload(
            title=title,
            asset_type=asset_type,
            filename=file.filename or f"upload.{ext}",
            data=data,
        )
    finally:
        await am.close()
    return {"asset_id": asset_id, "upload_url": upload_url, "type": asset_type}


def _asset_row_to_status_payload(row) -> dict[str, Any]:
    aid = str(row["id"])
    raw_title = row.get("title")
    title_str = (raw_title or "").strip() if raw_title is not None else ""
    return {
        "asset_id": aid,
        "title": title_str,
        "asset_type": row["type"],
        "status": row["status"],
        "asset_raw_path": row["upload_path"],
        "asset_processed_path": row["process_path"] or "",
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "retry_count": 0,
    }


def _parse_stored_citations(citations_raw: Any) -> list[dict[str, Any]]:
    if citations_raw is None:
        return []
    if isinstance(citations_raw, str):
        try:
            citations_raw = json.loads(citations_raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(citations_raw, list):
        return []
    return [x for x in citations_raw if isinstance(x, dict)][:16]


def _evidence_from_last_assistant(msgs: list[Any]) -> list[dict[str, Any]]:
    """Use citations on the latest llm message (Evidence-shaped list from hybrid_search)."""
    for m in reversed(msgs):
        role = m["role"] if hasattr(m, "__getitem__") else getattr(m, "role", None)
        if role != "llm":
            continue
        cit = m["citations"] if hasattr(m, "__getitem__") else getattr(m, "citations", None)
        ev = _parse_stored_citations(cit)
        if ev:
            return ev
    return []


def _raw_path_from_upload_url(upload_url: str) -> str:
    if "/static/storage/" in upload_url:
        return "/static/" + upload_url.split("/static/", 1)[1]
    if upload_url.startswith("/static/"):
        return upload_url
    return upload_url


@app.post("/api/v1/assets/sync", tags=["assets"])
async def sync_assets(asset_id: str | None = Query(None)) -> dict[str, Any]:
    am = AssetManager()
    await am.connect()
    try:
        if asset_id:
            db = get_database()
            row = await db.fetchrow("SELECT type, status FROM assets WHERE id = $1", uuid.UUID(asset_id))
            if not row:
                raise HTTPException(404, "asset not found")
            if row["type"] == "pdf":
                job_id = await am.enqueue_pdf_pipeline(asset_id)
            else:
                job_id = await am.enqueue_video_pipeline(asset_id)
            return {"status": "success", "asset_id": asset_id, "job_id": job_id, "message": "queued"}
        rows = await get_database().fetch(
            "SELECT id, type FROM assets WHERE status = 'Raw' ORDER BY created_at ASC"
        )
        jobs = 0
        for r in rows:
            aid = str(r["id"])
            if r["type"] == "pdf":
                await am.enqueue_pdf_pipeline(aid)
            else:
                await am.enqueue_video_pipeline(aid)
            jobs += 1
        return {"status": "success", "message": f"started {jobs} pipelines", "queued": jobs}
    finally:
        await am.close()


@app.get("/api/v1/status/single_asset", tags=["status_preview"])
async def single_asset_status(asset_id: str | None = Query(None)) -> dict[str, Any]:
    db = get_database()
    if asset_id:
        row = await db.fetchrow(
            "SELECT id, title, type, status, upload_path, process_path, created_at FROM assets WHERE id = $1",
            uuid.UUID(asset_id),
        )
        if not row:
            raise HTTPException(404, "not found")
        return {"status": "success", "data": _asset_row_to_status_payload(row)}
    rows = await db.fetch(
        "SELECT id, title, type, status, upload_path, process_path, created_at FROM assets ORDER BY created_at DESC"
    )
    data = {str(r["id"]): _asset_row_to_status_payload(r) for r in rows}
    return {"status": "success", "data": data}


@app.get("/api/v1/assets/structure", tags=["status_preview"])
async def asset_structure(asset_id: str = Query(...)) -> dict[str, Any]:
    db = get_database()
    row = await db.fetchrow(
        "SELECT structure_outline, status FROM assets WHERE id = $1",
        uuid.UUID(asset_id),
    )
    if not row:
        raise HTTPException(404, "not found")
    outline = outline_to_frontend(row["structure_outline"] if isinstance(row["structure_outline"], list) else [])
    if row["status"] == "Ready" and outline:
        st = "success"
    elif row["status"] == "Failed":
        st = "error"
    else:
        st = "processing"
    return {
        "status": st,
        "data": {"title": "", "outline": {"outline": outline}},
        "current_step": row["status"],
    }


@app.get("/api/v1/assets/preview", tags=["status_preview"])
async def asset_preview(asset_id: str = Query(...)) -> dict[str, Any]:
    db = get_database()
    row = await db.fetchrow(
        "SELECT type, upload_path, process_path FROM assets WHERE id = $1",
        uuid.UUID(asset_id),
    )
    if not row:
        raise HTTPException(404, "not found")
    raw_path = _raw_path_from_upload_url(row["upload_path"] or "")
    return {
        "asset_id": asset_id,
        "type": row["type"],
        "raw_path": raw_path,
        "process_url": row["process_path"],
    }


@app.get("/api/v1/status/single_chat", tags=["chats"])
async def single_chat_status(chat_id: str | None = Query(None)) -> dict[str, Any]:
    db = get_database()
    if chat_id:
        row = await db.fetchrow(
            "SELECT id, title, status, created_at FROM sessions WHERE id = $1",
            uuid.UUID(chat_id),
        )
        if not row:
            return {"status": "success", "data": {}}
        msgs = await db.fetch(
            """
            SELECT role, content, term, created_at, citations
            FROM chat_messages WHERE session_id = $1
            ORDER BY term ASC
            """,
            uuid.UUID(chat_id),
        )
        messages = []
        for m in msgs:
            role = m["role"]
            if role == "llm":
                role = "assistant"
            messages.append(
                {
                    "role": role,
                    "message": m["content"],
                    "timestamp": m["created_at"].isoformat() if m["created_at"] else "",
                }
            )
        sid = str(row["id"])
        evidence = _evidence_from_last_assistant(list(msgs))
        data = {
            sid: {
                "chat_id": sid,
                "chat_name": row["title"] or "Chat",
                "status": row["status"],
                "messages": messages,
                "evidence": evidence,
                "last_active": row["created_at"].isoformat() if row["created_at"] else "",
            }
        }
        return {"status": "success", "data": data}

    rows = await db.fetch("SELECT id, title, status, created_at FROM sessions ORDER BY created_at DESC LIMIT 50")
    data: dict[str, Any] = {}
    for row in rows:
        sid = str(row["id"])
        msgs = await db.fetch(
            """
            SELECT role, content, term, created_at, citations
            FROM chat_messages WHERE session_id = $1
            ORDER BY term ASC
            """,
            uuid.UUID(sid),
        )
        messages = []
        for m in msgs:
            role = m["role"]
            if role == "llm":
                role = "assistant"
            messages.append(
                {
                    "role": role,
                    "message": m["content"],
                    "timestamp": m["created_at"].isoformat() if m["created_at"] else "",
                }
            )
        evidence = _evidence_from_last_assistant(list(msgs))
        data[sid] = {
            "chat_id": sid,
            "chat_name": row["title"] or "Chat",
            "status": row["status"],
            "messages": messages,
            "evidence": evidence,
            "last_active": row["created_at"].isoformat() if row["created_at"] else "",
        }
    return {"status": "success", "data": data}


class ChatCreateBody(BaseModel):
    title: str | None = None


@app.post("/api/v1/chats/create", tags=["chats"])
async def chats_create(body: ChatCreateBody | None = None) -> dict[str, str]:
    sm = SessionManager()
    await sm.connect()
    try:
        sid = await sm.create_session(title=(body.title if body else None))
    finally:
        await sm.close()
    return {"chat_id": sid}


@app.get("/api/v1/chats/stream", tags=["chats"])
async def chats_stream(
    chat_id: str = Query(...),
    message: str = Query(...),
):
    async def gen():
        sm = SessionManager()
        await sm.connect()
        try:
            await sm.append_message(chat_id, "user", message)
            pm = PromptManager()
            async for chunk in run_chat_turn(chat_id, message, sm, pm):
                yield {"data": json.dumps(chunk)}
        finally:
            await sm.close()

    return EventSourceResponse(gen())


# --- Expert register & audit (phase 5) ---


class ExpertCreate(BaseModel):
    display_name: str
    email: str | None = None
    roles: list[str] = []


@app.get("/api/v1/experts", tags=["experts_audit"])
async def list_experts() -> dict[str, Any]:
    db = get_database()
    rows = await db.fetch(
        "SELECT id, display_name, email, roles, created_at FROM expert_register ORDER BY created_at DESC LIMIT 200"
    )
    return {
        "status": "success",
        "data": [
            {
                "expert_id": str(r["id"]),
                "display_name": r["display_name"],
                "email": r["email"],
                "roles": r["roles"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@app.post("/api/v1/experts", tags=["experts_audit"])
async def create_expert(body: ExpertCreate) -> dict[str, str]:
    db = get_database()
    eid = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO expert_register (id, display_name, email, roles)
        VALUES ($1, $2, $3, $4)
        """,
        eid,
        body.display_name,
        body.email,
        body.roles,
    )
    return {"expert_id": str(eid)}


class AuditBody(BaseModel):
    expert_id: str
    entity_id: str
    field_name: str
    old_value: Any = None
    new_value: Any = None
    reason: str | None = None


@app.post("/api/v1/audit/confidence", tags=["experts_audit"])
async def audit_confidence(body: AuditBody) -> dict[str, str]:
    db = get_database()
    await db.execute(
        """
        INSERT INTO audit_logs (expert_id, entity_id, field_name, old_value, new_value, reason)
        VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, $5::jsonb, $6)
        """,
        uuid.UUID(body.expert_id),
        uuid.UUID(body.entity_id),
        body.field_name,
        json.dumps(body.old_value),
        json.dumps(body.new_value),
        body.reason,
    )
    return {"status": "ok"}
