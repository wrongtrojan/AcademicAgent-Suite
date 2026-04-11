"""Hybrid retrieval: PostgreSQL ts_rank_cd (BM25-like) + dense cosine + entity confidence."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

import asyncpg

from shared.database.pool import get_database
from shared.embedding import cosine, embed_text
from shared.evidence_format import evidence_metadata_for_chunk

logger = logging.getLogger(__name__)

W_BM25 = 0.25
W_VECTOR = 0.15
W_ENTITY = 0.60


def _keyword_overlap(query: str, text: str | None) -> float:
    if not text:
        return 0.0
    qtok = {t.lower() for t in re.findall(r"[\w\u4e00-\u9fff]+", query)}
    ttok = {t.lower() for t in re.findall(r"[\w\u4e00-\u9fff]+", text)}
    if not qtok:
        return 0.0
    inter = len(qtok & ttok)
    return min(1.0, inter / max(1, len(qtok)))


_SQL_BASE = """
SELECT ac.id, ac.assets_id, ac.content, ac.coordination, ac.dense_embedding,
  a.type AS asset_type,
  COALESCE((
    SELECT MAX(em.confidence) FROM entity_mentions em WHERE em.chunk_id = ac.id
  ), 0.0) AS max_conf,
  COALESCE((
    SELECT COUNT(*)::int FROM entity_mentions em WHERE em.chunk_id = ac.id
  ), 0) AS mention_count
FROM asset_chunks ac
INNER JOIN assets a ON a.id = ac.assets_id
"""

_SQL_TS = """
SELECT ac.id, ac.assets_id, ac.content, ac.coordination, ac.dense_embedding,
  a.type AS asset_type,
  ts_rank_cd(ac.content_tsv, plainto_tsquery('simple', $1)) AS ts_r,
  COALESCE((
    SELECT MAX(em.confidence) FROM entity_mentions em WHERE em.chunk_id = ac.id
  ), 0.0) AS max_conf,
  COALESCE((
    SELECT COUNT(*)::int FROM entity_mentions em WHERE em.chunk_id = ac.id
  ), 0) AS mention_count
FROM asset_chunks ac
INNER JOIN assets a ON a.id = ac.assets_id
"""


async def _fetch_rows_ts(
    db, q: str, asset_ids: list[str] | None
) -> list[asyncpg.Record]:
    if asset_ids:
        uuids = [uuid.UUID(a) for a in asset_ids]
        return await db.fetch(
            _SQL_TS
            + " WHERE ac.assets_id = ANY($2::uuid[]) ORDER BY ts_r DESC NULLS LAST LIMIT 800",
            q,
            uuids,
        )
    return await db.fetch(_SQL_TS + " ORDER BY ts_r DESC NULLS LAST LIMIT 800", q)


async def _fetch_rows_plain(db, asset_ids: list[str] | None) -> list[asyncpg.Record]:
    if asset_ids:
        uuids = [uuid.UUID(a) for a in asset_ids]
        return await db.fetch(_SQL_BASE + " WHERE ac.assets_id = ANY($1::uuid[]) LIMIT 800", uuids)
    return await db.fetch(_SQL_BASE + " LIMIT 800")


async def hybrid_search(
    query: str,
    *,
    asset_ids: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    db = get_database()
    q = (query or "").strip()
    qvec = embed_text(q if q else " ")

    rows: list[asyncpg.Record] = []
    has_ts = False
    if q:
        try:
            rows = await _fetch_rows_ts(db, q, asset_ids)
            has_ts = True
        except asyncpg.UndefinedColumnError:
            logger.warning("content_tsv missing; apply migration 002_fulltext_embedding.sql")
            rows = await _fetch_rows_plain(db, asset_ids)
        except asyncpg.PostgresError as exc:
            logger.warning("full-text query failed (%s); using fallback rows", exc)
            rows = await _fetch_rows_plain(db, asset_ids)
    else:
        rows = await _fetch_rows_plain(db, asset_ids)

    max_ts = max((float(r["ts_r"]) for r in rows if has_ts and "ts_r" in r), default=0.0) or 1.0

    scored: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        text = r["content"] or ""
        if has_ts and "ts_r" in r:
            bm25_n = min(1.0, float(r["ts_r"] or 0.0) / max_ts)
        else:
            bm25_n = _keyword_overlap(q, text) if q else 0.0

        vec = 0.0
        emb = r["dense_embedding"]
        if emb is not None and len(emb) > 0:
            try:
                if len(qvec) != len(emb):
                    vec = 0.0
                else:
                    vec = max(0.0, cosine(qvec.tolist(), list(map(float, emb))))
            except Exception:
                vec = 0.0

        ent = float(r["max_conf"] or 0.0)
        if r["mention_count"] and r["mention_count"] > 0:
            ent = min(1.0, ent + 0.05 * int(r["mention_count"]))

        score = W_BM25 * bm25_n + W_VECTOR * vec + W_ENTITY * ent
        aid = str(r["assets_id"])
        atype = r["asset_type"] or "pdf"
        coord = r["coordination"]
        if isinstance(coord, str):
            try:
                coord = json.loads(coord)
            except Exception:
                coord = {}
        meta = evidence_metadata_for_chunk(coord, atype, aid)
        scored.append(
            (
                score,
                {
                    "chunk_id": str(r["id"]),
                    "asset_id": aid,
                    "content": text,
                    "score": score,
                    "bm25": bm25_n,
                    "vec": vec,
                    "entity": ent,
                    "metadata": meta,
                },
            )
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:limit]]


async def process_search_job(env) -> dict[str, Any]:
    payload = env.payload or {}
    query = payload.get("query") or ""
    asset_ids = payload.get("asset_ids")
    limit = int(payload.get("limit", 10))
    rows = await hybrid_search(query, asset_ids=asset_ids, limit=limit)
    return {"hits": rows}
