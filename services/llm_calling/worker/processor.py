from __future__ import annotations

import logging
import os

import httpx

from shared.protocol.envelope import TaskResult, TaskStatus

logger = logging.getLogger(__name__)


async def process_llm(env) -> TaskResult:
    payload = env.payload or {}
    prompt = payload.get("prompt") or payload.get("user_message") or ""
    key = os.environ.get("OPENAI_API_KEY", "")
    base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    if not key:
        text = f"[offline-llm] {prompt[:4000]}"
        return TaskResult(
            job_id=env.job_id,
            service=env.service,
            status=TaskStatus.completed,
            session_id=env.session_id,
            data={"text": text},
        )
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
    return TaskResult(
        job_id=env.job_id,
        service=env.service,
        status=TaskStatus.completed,
        session_id=env.session_id,
        data={"text": text},
    )
