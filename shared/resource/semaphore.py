from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from shared.protocol.envelope import ServiceName


def _limit_override(svc: ServiceName) -> int | None:
    key = f"CONTEXTMAP_LIMIT_{svc.name.upper()}"
    raw = os.environ.get(key, "").strip()
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


@dataclass
class ServiceLimits:
    """Per-service concurrency caps (process-local)."""

    limits: dict[ServiceName, int]

    @classmethod
    def default(cls) -> "ServiceLimits":
        return cls(
            {
                ServiceName.pdf_recognition: 2,
                ServiceName.video_recognition: 1,
                ServiceName.data_embedding: 4,
                ServiceName.data_ingesting: 4,
                ServiceName.sandbox_inference: 2,
                ServiceName.visual_inference: 2,
                ServiceName.llm_calling: 8,
                ServiceName.mixture_searching: 8,
            }
        )

    @classmethod
    def from_env(cls) -> "ServiceLimits":
        """Defaults with optional CONTEXTMAP_LIMIT_<ENUM_NAME> overrides (e.g. CONTEXTMAP_LIMIT_PDF_RECOGNITION=1)."""
        merged = dict(cls.default().limits)
        for svc in ServiceName:
            ov = _limit_override(svc)
            if ov is not None:
                merged[svc] = ov
        return cls(merged)


class ServiceResourceGate:
    """Asyncio semaphores for coordinating heavy workers in service_manager."""

    def __init__(self, limits: ServiceLimits | None = None):
        self._limits = limits or ServiceLimits.default()
        self._locks: dict[ServiceName, asyncio.Semaphore] = {
            svc: asyncio.Semaphore(n) for svc, n in self._limits.limits.items()
        }

    async def acquire(self, service: ServiceName) -> None:
        await self._locks[service].acquire()

    def release(self, service: ServiceName) -> None:
        self._locks[service].release()

    async def __aenter__(self) -> "ServiceResourceGate":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None
