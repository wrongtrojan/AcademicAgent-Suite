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

setup_logging("mixture_searching")

from shared.database.pool import get_database
from shared.messaging.redis_streams import JobBroker, StreamsConfig, work_stream
from shared.protocol.envelope import ServiceName
from services.mixture_searching.worker.processor import process_search_job

logger = logging.getLogger("mixture_searching")


async def run() -> None:
    await get_database().connect()
    svc = ServiceName.mixture_searching
    broker = JobBroker(
        StreamsConfig(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            consumer_name=os.environ.get("WORKER_CONSUMER", "mix-1"),
        )
    )
    await broker.connect()
    await broker.ensure_groups([svc])
    stream = work_stream(svc)
    while True:
        batch = await broker.read_work(svc, count=1, block_ms=8000)
        for entry_id, env in batch:
            try:
                result = await process_search_job(env)
                logger.info("search job %s hits=%s", env.job_id, len(result.get("hits", [])))
            except Exception:
                logger.exception("search failed")
            finally:
                await broker.ack(stream, entry_id)


if __name__ == "__main__":
    asyncio.run(run())
