from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import asyncpg

from shared.http_utils import fetch_url_bytes
from shared.messaging.redis_streams import JobBroker, StreamsConfig
from shared.paths import storage_root
from shared.messaging.reliability import record_job_pending
from shared.protocol.envelope import OutputSpec, ServiceName, TaskEnvelope, TaskResult, TaskStatus
from services.pdf_recognition.worker.mineru_runner import run_mineru_extract

logger = logging.getLogger(__name__)


def _public_url_for_path(rel: Path) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/static/storage/{rel.as_posix()}"


async def process_pdf(env: TaskEnvelope) -> TaskResult:
    if not env.asset_id:
        raise ValueError("pdf_recognition requires asset_id")
    asset_id = env.asset_id
    payload = env.payload or {}
    process_rel = Path(payload.get("process_dir_rel", f"processed/pdf/{asset_id}"))
    process_dir = storage_root() / process_rel
    process_dir.mkdir(parents=True, exist_ok=True)

    raw_url = env.input_refs[0]
    pdf_bytes = await fetch_url_bytes(raw_url)
    local_pdf = process_dir / "source.pdf"
    local_pdf.write_bytes(pdf_bytes)

    md_dir = process_dir / "mineru_out"
    md_dir.mkdir(exist_ok=True)
    if not run_mineru_extract(local_pdf, md_dir):
        logger.warning("MinerU/magic-pdf did not produce output; using synthetic chunks if needed")

    chunks: list[dict] = []
    for p in sorted(process_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".md", ".json", ".txt"):
            continue
        if p.name == "manifest.json":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[:8000]
            if text.strip():
                chunks.append(
                    {
                        "content": text,
                        "type": "text",
                        "coordination": {"page": 1, "source": p.name},
                    }
                )
        except OSError:
            continue
    if not chunks:
        chunks = [
            {
                "content": f"Synthetic chunk for asset {asset_id} (enable magic-pdf for real OCR).",
                "type": "text",
                "coordination": {"page": 1},
            }
        ]

    manifest = {
        "asset_id": asset_id,
        "chunks": chunks,
    }
    manifest_path = process_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    manifest_url = _public_url_for_path(process_rel / "manifest.json")

    db_url = os.environ.get(
        "DATABASE_URL", "postgresql://contextmap:contextmap@localhost:5432/contextmap"
    )
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(
            "UPDATE assets SET status = $2, process_path = COALESCE(process_path, $3) WHERE id = $1::uuid",
            asset_id,
            "Structuring",
            manifest_url,
        )
    finally:
        await conn.close()

    # Chain embedding stage
    broker = JobBroker(
        StreamsConfig(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            consumer_name="pdf-chain",
        )
    )
    await broker.connect()
    try:
        next_env = TaskEnvelope(
            service=ServiceName.data_embedding,
            status=TaskStatus.pending,
            input_refs=[manifest_url],
            output=OutputSpec(),
            asset_id=asset_id,
            idempotency_key=f"{asset_id}:data_embedding",
            payload={"process_dir_rel": process_rel.as_posix(), "stage": "embed"},
        )
        await record_job_pending(next_env)
        await broker.publish_ingress(next_env)
    finally:
        await broker.close()

    return TaskResult(
        job_id=env.job_id,
        service=env.service,
        status=TaskStatus.completed,
        asset_id=asset_id,
        output_refs=[manifest_url],
        data={"manifest": str(manifest_path)},
    )
