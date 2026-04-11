from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path

import asyncpg
import httpx

from shared.http_utils import rewrite_localhost_gateway_url
from shared.paths import storage_root
from shared.protocol.envelope import TaskResult, TaskStatus

logger = logging.getLogger(__name__)

ENTITY_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _entity_id(categories: list[str], canonical_name: str) -> uuid.UUID:
    key = "::".join(sorted(categories)) + "||" + canonical_name.strip().lower()
    return uuid.uuid5(ENTITY_NS, key)


def _title_and_summary(content: str) -> tuple[str, str]:
    """First line as title headline; remainder (trimmed) as summary for outline UI."""
    text = (content or "").strip()
    if not text:
        return "", ""
    parts = text.split("\n", 1)
    title = parts[0].strip()[:120]
    rest = parts[1].strip() if len(parts) > 1 else ""
    summary = rest[:400] if rest else ""
    return title, summary


async def process_ingest(env) -> TaskResult:
    url = rewrite_localhost_gateway_url(env.input_refs[0])
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        embedded = r.json()

    asset_id = embedded.get("asset_id") or env.asset_id
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://contextmap:contextmap@localhost:5432/contextmap",
    )
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(
            "DELETE FROM asset_chunks WHERE assets_id = $1::uuid",
            asset_id,
        )
        outline = []
        for idx, ch in enumerate(embedded.get("chunks", [])):
            chunk_id = uuid.uuid4()
            coord = ch.get("coordination") or {}
            dense = ch.get("dense_embedding") or []
            sparse = ch.get("sparse_embedding") or {}
            await conn.execute(
                """
                INSERT INTO asset_chunks (
                  id, assets_id, content, visual_description, type, coordination, dense_embedding, sparse_embedding
                ) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::jsonb, $7::real[], $8::jsonb)
                """,
                chunk_id,
                asset_id,
                ch.get("content"),
                ch.get("visual_description"),
                ch.get("type", "text"),
                json.dumps(coord),
                dense,
                json.dumps(sparse),
            )
            title, summary = _title_and_summary(ch.get("content") or "")
            if not title:
                title = f"Section {idx+1}"
            anchor = float((coord.get("page") or coord.get("timestamp_start") or idx + 1))
            outline.append(
                {
                    "id": str(chunk_id),
                    "title": title,
                    "summary": summary,
                    "anchor": anchor,
                    "children": [],
                }
            )

            for m in re.findall(
                r"[\u4e00-\u9fff]{2,8}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*",
                ch.get("content") or "",
            ):
                name = m.strip()
                if len(name) < 2:
                    continue
                cats = ["general"]
                eid = _entity_id(cats, name)
                await conn.execute(
                    """
                    INSERT INTO knowledge_entities (id, categories, canonical_name, aliases, description)
                    VALUES ($1::uuid, $2::text[], $3, $4::jsonb, $5)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    eid,
                    cats,
                    name,
                    json.dumps([]),
                    "auto-extracted",
                )
                await conn.execute(
                    """
                    INSERT INTO entity_mentions (entities_id, chunk_id, confidence, context)
                    VALUES ($1::uuid, $2::uuid, $3, $4)
                    """,
                    eid,
                    chunk_id,
                    0.55,
                    (ch.get("content") or "")[:400],
                )

        await conn.execute(
            """
            UPDATE assets SET status = 'Ready', structure_outline = $2::jsonb
            WHERE id = $1::uuid
            """,
            asset_id,
            json.dumps(outline),
        )
    finally:
        await conn.close()

    return TaskResult(
        job_id=env.job_id,
        service=env.service,
        status=TaskStatus.completed,
        asset_id=str(asset_id),
        data={"chunks": len(embedded.get("chunks", []))},
    )
