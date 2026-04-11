"""Job idempotency and lifecycle using job_records."""

from __future__ import annotations

import json
import logging
import uuid

from shared.database.pool import get_database
from shared.protocol.envelope import TaskEnvelope

logger = logging.getLogger(__name__)


async def should_route_job(env: TaskEnvelope) -> bool:
    """If False, skip routing (already completed with same idempotency key)."""
    if not env.idempotency_key:
        return True
    db = get_database()
    row = await db.fetchrow(
        "SELECT status FROM job_records WHERE idempotency_key = $1",
        env.idempotency_key,
    )
    if row and row["status"] == "completed":
        logger.info("skip duplicate idempotency_key=%s", env.idempotency_key)
        return False
    return True


async def record_job_pending(env: TaskEnvelope) -> None:
    if not env.idempotency_key:
        return
    db = get_database()
    payload = env.model_dump(mode="json")
    await db.execute(
        """
        INSERT INTO job_records (job_id, idempotency_key, service, status, payload)
        VALUES ($1::uuid, $2, $3, 'pending', $4::jsonb)
        ON CONFLICT (idempotency_key) DO UPDATE SET
          job_id = EXCLUDED.job_id,
          service = EXCLUDED.service,
          status = 'pending',
          payload = EXCLUDED.payload,
          updated_at = now()
        """,
        uuid.UUID(env.job_id),
        env.idempotency_key,
        env.service.value,
        json.dumps(payload),
    )


async def mark_job_completed(job_id: str) -> None:
    db = get_database()
    await db.execute(
        "UPDATE job_records SET status = 'completed', updated_at = now() WHERE job_id = $1::uuid",
        uuid.UUID(job_id),
    )


async def mark_job_failed(job_id: str, message: str | None = None) -> None:
    db = get_database()
    await db.execute(
        """
        UPDATE job_records SET status = 'failed', updated_at = now()
        WHERE job_id = $1::uuid
        """,
        uuid.UUID(job_id),
    )


