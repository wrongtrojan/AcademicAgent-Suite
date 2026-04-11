from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx

from shared.embedding import embed_text
from shared.http_utils import rewrite_localhost_gateway_url
from shared.messaging.redis_streams import JobBroker, StreamsConfig
from shared.messaging.reliability import record_job_pending
from shared.paths import storage_root
from shared.protocol.envelope import OutputSpec, ServiceName, TaskEnvelope, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


def _public_url(rel: Path) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/static/storage/{rel.as_posix()}"


async def process_embedding(env: TaskEnvelope) -> TaskResult:
    manifest_url = rewrite_localhost_gateway_url(env.input_refs[0])
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(manifest_url)
        r.raise_for_status()
        manifest = r.json()

    asset_id = manifest.get("asset_id") or env.asset_id
    payload = env.payload or {}
    process_rel = Path(payload.get("process_dir_rel", f"processed/pdf/{asset_id}"))
    process_dir = storage_root() / process_rel

    out_chunks = []
    for ch in manifest.get("chunks", []):
        text = ch.get("content") or ""
        vec = embed_text(text)
        keywords = sorted({w.lower() for w in text.split() if len(w) > 3})[:32]
        out_chunks.append(
            {
                **ch,
                "dense_embedding": vec.tolist(),
                "sparse_embedding": {"keywords": keywords},
            }
        )

    embedded = {"asset_id": asset_id, "chunks": out_chunks}
    out_path = process_dir / "manifest_embedded.json"
    out_path.write_text(json.dumps(embedded, ensure_ascii=False), encoding="utf-8")
    out_url = _public_url(process_rel / "manifest_embedded.json")

    broker = JobBroker(
        StreamsConfig(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            consumer_name="embed-chain",
        )
    )
    await broker.connect()
    try:
        next_env = TaskEnvelope(
            service=ServiceName.data_ingesting,
            status=TaskStatus.pending,
            input_refs=[out_url],
            output=OutputSpec(),
            asset_id=str(asset_id),
            idempotency_key=f"{asset_id}:data_ingesting",
            payload={"process_dir_rel": process_rel.as_posix(), "stage": "ingest"},
        )
        await record_job_pending(next_env)
        await broker.publish_ingress(next_env)
    finally:
        await broker.close()

    return TaskResult(
        job_id=env.job_id,
        service=env.service,
        status=TaskStatus.completed,
        asset_id=str(asset_id),
        output_refs=[out_url],
    )
