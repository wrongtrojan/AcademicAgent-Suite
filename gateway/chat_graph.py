"""LangGraph-based chat turn: retrieve context, render prompt, complete LLM (or offline echo)."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, AsyncIterator

from pathlib import Path

from typing_extensions import TypedDict

from compiler.translator import build_workflow_from_dsl
from core.prompt_manager import PromptManager
from gateway.chat_hooks import post_retrieve_hooks
from core.session_manager import SessionManager
from services.mixture_searching.worker.processor import hybrid_search
from shared.database.pool import get_database
from shared.evidence_format import hit_to_evidence

logger = logging.getLogger(__name__)


class ChatState(TypedDict, total=False):
    session_id: str
    user_message: str
    context: str
    answer: str
    retrieval_hits: list[dict[str, Any]]


_DSL = Path(__file__).resolve().parents[1] / "compiler" / "dsl" / "workflow.yaml"


async def retrieve_node(state: ChatState) -> ChatState:
    rows = await hybrid_search(state["user_message"], limit=12)
    parts = []
    for r in rows:
        bm = r.get("bm25", r.get("kw", 0))
        parts.append(
            f"[chunk={r['chunk_id']} score={r['score']:.3f} bm25={bm:.3f}]\n{(r['content'] or '')[:800]}"
        )
    ctx = "\n\n".join(parts) if parts else "(no retrieved chunks)"
    return {**state, "context": ctx, "retrieval_hits": rows}


async def synthesize_node(state: ChatState) -> ChatState:
    pm = PromptManager()
    text = await pm.render(
        "synthesizer",
        {"context": state["context"], "user_message": state["user_message"]},
    )
    answer = await _llm_complete(text)
    return {**state, "answer": answer}


async def _llm_complete(prompt: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    if not key:
        return f"[offline-llm] {prompt[:2000]}"
    try:
        import httpx

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
            return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return f"[llm-error] {exc}"


_graph = build_workflow_from_dsl(
    _DSL,
    ChatState,
    {
        "retrieve": retrieve_node,
        "post_retrieve_hooks": post_retrieve_hooks,
        "synthesize": synthesize_node,
    },
)


async def run_chat_turn(
    session_id: str,
    user_message: str,
    sm: SessionManager,
    _pm: PromptManager | None = None,
) -> AsyncIterator[dict[str, Any]]:
    db = get_database()
    await db.execute(
        "UPDATE sessions SET status = $2 WHERE id = $1",
        uuid.UUID(session_id),
        "Researching",
    )
    state = await _graph.ainvoke(
        {
            "session_id": session_id,
            "user_message": user_message,
            "context": "",
            "answer": "",
            "retrieval_hits": [],
        }
    )
    answer = state.get("answer", "")
    hits = state.get("retrieval_hits") or []
    citations_payload = [hit_to_evidence(h) for h in hits]
    step = max(1, len(answer) // 40)
    for i in range(0, len(answer), step):
        yield {"status": "processing", "content": answer[i : i + step]}
    await sm.append_message(session_id, "llm", answer, citations=citations_payload)
    await db.execute(
        "UPDATE sessions SET status = $2 WHERE id = $1",
        uuid.UUID(session_id),
        "Idle",
    )
    yield {"status": "completed", "content": ""}
