"""Routes tasks from ingress to per-service work streams with concurrency gates."""

from __future__ import annotations

import asyncio
import logging
import os

from shared.database.pool import get_database
from shared.logging_config import setup_logging
from shared.messaging.redis_streams import STREAM_INGRESS, JobBroker, StreamsConfig
from shared.messaging.reliability import should_route_job
from shared.protocol.envelope import ServiceName, TaskEnvelope, TaskResult, TaskStatus
from shared.resource.semaphore import ServiceLimits, ServiceResourceGate

logger = logging.getLogger(__name__)


class ServiceManager:
    def __init__(self) -> None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        consumer = os.environ.get("SERVICE_MANAGER_CONSUMER", "sm-1")
        self._broker = JobBroker(StreamsConfig(redis_url=redis_url, consumer_name=consumer))
        self._gate = ServiceResourceGate(ServiceLimits.from_env())
        self._running = False

    async def start(self) -> None:
        await get_database().connect()
        await self._broker.connect()
        await self._broker.ensure_groups(list(ServiceName))
        self._running = True
        logger.info("ServiceManager connected; routing %s -> work streams", STREAM_INGRESS)

    async def stop(self) -> None:
        self._running = False
        await self._broker.close()
        await get_database().close()

    async def route_loop(self) -> None:
        assert self._running
        while self._running:
            try:
                batch = await self._broker.read_ingress(count=8, block_ms=8000)
                for entry_id, env in batch:
                    await self._route_one(entry_id, env)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ingress batch failed")

    async def _route_one(self, entry_id: str, env: TaskEnvelope) -> None:
        if not await should_route_job(env):
            await self._broker.ack(STREAM_INGRESS, entry_id)
            return
        await self._gate.acquire(env.service)
        try:
            await self._broker.publish_work(env)
            await self._broker.ack(STREAM_INGRESS, entry_id)
            logger.info("routed job %s -> %s", env.job_id, env.service.value)
        except Exception as exc:
            logger.exception("route failed for %s: %s", env.job_id, exc)
            res = TaskResult(
                job_id=env.job_id,
                service=env.service,
                status=TaskStatus.failed,
                asset_id=env.asset_id,
                session_id=env.session_id,
                error_code="ROUTING_FAILED",
                message=str(exc),
            )
            await self._broker.publish_dlq(res)
            await self._broker.ack(STREAM_INGRESS, entry_id)
        finally:
            self._gate.release(env.service)


async def run_service_manager() -> None:
    setup_logging("service_manager")
    sm = ServiceManager()
    await sm.start()
    try:
        await sm.route_loop()
    finally:
        await sm.stop()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_service_manager())
