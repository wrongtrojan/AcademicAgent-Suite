from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from shared.logging_config import setup_logging

setup_logging("pdf_recognition")

from shared.database.pool import get_database
from shared.messaging.redis_streams import JobBroker, StreamsConfig, work_stream
from shared.messaging.reliability import mark_job_completed, mark_job_failed
from shared.protocol.envelope import ServiceName
from services.pdf_recognition.worker.processor import process_pdf

logger = logging.getLogger("pdf_recognition")


async def run() -> None:
    svc = ServiceName.pdf_recognition
    broker = JobBroker(
        StreamsConfig(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            consumer_name=os.environ.get("WORKER_CONSUMER", "pdf-1"),
        )
    )
    await get_database().connect()
    await broker.connect()
    await broker.ensure_groups([svc])
    stream = work_stream(svc)
    logger.info("listening on %s", stream)
    while True:
        batch = await broker.read_work(svc, count=1, block_ms=8000)
        for entry_id, env in batch:
            try:
                res = await process_pdf(env)
                await mark_job_completed(env.job_id)
                logger.info("job %s completed: %s", env.job_id, res.output_refs)
            except Exception as exc:
                logger.exception("job failed: %s", exc)
                await mark_job_failed(env.job_id, str(exc))
            finally:
                await broker.ack(stream, entry_id)


if __name__ == "__main__":
    asyncio.run(run())
