from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

import redis.asyncio as redis

from shared.protocol.envelope import ServiceName, TaskEnvelope, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

STREAM_INGRESS = "cm:ingress"
STREAM_DLQ = "cm:dlq"
GROUP_DEFAULT = "cm-workers"


def work_stream(service: ServiceName) -> str:
    return f"cm:work:{service.value}"


@dataclass
class StreamsConfig:
    redis_url: str = "redis://localhost:6379/0"
    consumer_group: str = GROUP_DEFAULT
    consumer_name: str = "consumer-1"


class JobBroker:
    """Redis Streams helper: ingress routing, per-service work queues, DLQ."""

    def __init__(self, cfg: StreamsConfig):
        self._cfg = cfg
        self._r: redis.Redis | None = None

    async def connect(self) -> None:
        self._r = redis.from_url(self._cfg.redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._r:
            await self._r.aclose()
            self._r = None

    @property
    def redis(self) -> redis.Redis:
        if not self._r:
            raise RuntimeError("JobBroker not connected")
        return self._r

    async def ensure_groups(self, services: list[ServiceName]) -> None:
        """Create consumer groups for ingress and each work stream."""
        r = self.redis
        for stream in [STREAM_INGRESS, STREAM_DLQ] + [work_stream(s) for s in services]:
            try:
                await r.xgroup_create(stream, self._cfg.consumer_group, id="0", mkstream=True)
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def publish_ingress(self, envelope: TaskEnvelope) -> str:
        payload = envelope.model_dump(mode="json")
        return await self.redis.xadd(STREAM_INGRESS, {"data": json.dumps(payload)})

    async def publish_work(self, envelope: TaskEnvelope) -> str:
        stream = work_stream(envelope.service)
        payload = envelope.model_dump(mode="json")
        return await self.redis.xadd(stream, {"data": json.dumps(payload)})

    async def publish_dlq(self, result: TaskResult, raw: dict[str, Any] | None = None) -> str:
        body = {"data": json.dumps(result.model_dump(mode="json")), "raw": json.dumps(raw or {})}
        return await self.redis.xadd(STREAM_DLQ, body)

    async def read_ingress(
        self,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[tuple[str, TaskEnvelope]]:
        r = self.redis
        streams = await r.xreadgroup(
            self._cfg.consumer_group,
            self._cfg.consumer_name,
            {STREAM_INGRESS: ">"},
            count=count,
            block=block_ms,
        )
        out: list[tuple[str, TaskEnvelope]] = []
        for _stream_name, entries in streams or []:
            for entry_id, fields in entries:
                raw = json.loads(fields["data"])
                out.append((entry_id, TaskEnvelope.model_validate(raw)))
        return out

    async def read_work(
        self,
        service: ServiceName,
        count: int = 1,
        block_ms: int = 5000,
    ) -> list[tuple[str, TaskEnvelope]]:
        stream = work_stream(service)
        r = self.redis
        streams = await r.xreadgroup(
            self._cfg.consumer_group,
            self._cfg.consumer_name,
            {stream: ">"},
            count=count,
            block=block_ms,
        )
        out: list[tuple[str, TaskEnvelope]] = []
        for _stream_name, entries in streams or []:
            for entry_id, fields in entries:
                raw = json.loads(fields["data"])
                out.append((entry_id, TaskEnvelope.model_validate(raw)))
        return out

    async def ack(self, stream: str, entry_id: str) -> None:
        await self.redis.xack(stream, self._cfg.consumer_group, entry_id)

    async def iterate_work(
        self,
        service: ServiceName,
        block_ms: int = 5000,
    ) -> AsyncIterator[tuple[str, TaskEnvelope]]:
        stream = work_stream(service)
        while True:
            streams = await self.redis.xreadgroup(
                self._cfg.consumer_group,
                self._cfg.consumer_name,
                {stream: ">"},
                count=1,
                block=block_ms,
            )
            if not streams:
                continue
            for _sn, entries in streams:
                for entry_id, fields in entries:
                    raw = json.loads(fields["data"])
                    yield entry_id, TaskEnvelope.model_validate(raw)
