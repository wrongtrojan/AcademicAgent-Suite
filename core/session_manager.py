"""Session initialization and chat-related persistence."""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from shared.database.pool import get_database
from shared.messaging.redis_streams import JobBroker, StreamsConfig
from shared.protocol.envelope import OutputSpec, ServiceName, TaskEnvelope, TaskStatus

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self) -> None:
        self._redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._broker: JobBroker | None = None

    async def connect(self) -> None:
        self._broker = JobBroker(StreamsConfig(redis_url=self._redis_url, consumer_name="session-mgr"))
        await self._broker.connect()

    async def close(self) -> None:
        if self._broker:
            await self._broker.close()
            self._broker = None

    async def create_session(self, title: str | None = None, config: dict[str, Any] | None = None) -> str:
        sid = str(uuid.uuid4())
        db = get_database()
        await db.execute(
            """
            INSERT INTO sessions (id, title, status, config)
            VALUES ($1, $2, 'Preparing', $3::jsonb)
            """,
            uuid.UUID(sid),
            title or "Chat",
            json.dumps(config or {}),
        )
        return sid

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        citations: list[Any] | None = None,
    ) -> int:
        db = get_database()
        row = await db.fetchrow(
            "SELECT COALESCE(MAX(term), -1) AS m FROM chat_messages WHERE session_id = $1",
            uuid.UUID(session_id),
        )
        term = int(row["m"]) + 1
        await db.execute(
            """
            INSERT INTO chat_messages (id, term, session_id, role, content, citations)
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5::jsonb)
            """,
            term,
            uuid.UUID(session_id),
            role,
            content,
            json.dumps(citations or []),
        )
        return term

    async def enqueue_llm_job(self, session_id: str, user_message: str) -> str:
        """Optional: publish llm_calling task (non-streaming batch)."""
        if not self._broker:
            await self.connect()
        assert self._broker is not None
        env = TaskEnvelope(
            service=ServiceName.llm_calling,
            status=TaskStatus.pending,
            input_refs=[os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000") + "/api/v1/health"],
            output=OutputSpec(),
            session_id=session_id,
            payload={"user_message": user_message, "mode": "chat"},
        )
        await self._broker.publish_ingress(env)
        return env.job_id
