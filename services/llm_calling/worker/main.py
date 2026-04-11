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

setup_logging("llm_calling")

from shared.messaging.redis_streams import JobBroker, StreamsConfig, work_stream
from shared.protocol.envelope import ServiceName
from services.llm_calling.worker.processor import process_llm

logger = logging.getLogger("llm_calling")


async def run() -> None:
    svc = ServiceName.llm_calling
    broker = JobBroker(
        StreamsConfig(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            consumer_name=os.environ.get("WORKER_CONSUMER", "llm-1"),
        )
    )
    await broker.connect()
    await broker.ensure_groups([svc])
    stream = work_stream(svc)
    while True:
        batch = await broker.read_work(svc, count=1, block_ms=8000)
        for entry_id, env in batch:
            try:
                await process_llm(env)
            except Exception:
                logger.exception("llm job failed")
            finally:
                await broker.ack(stream, entry_id)


if __name__ == "__main__":
    asyncio.run(run())
