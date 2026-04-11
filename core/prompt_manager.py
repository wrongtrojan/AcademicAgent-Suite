"""DB-backed prompt templates (slug, Jinja2); seeds from core/prompt_seed (migrated from main)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined

from shared.database.pool import get_database

logger = logging.getLogger(__name__)

_jinja = Environment(undefined=StrictUndefined, autoescape=False)

_SEED_DIR = Path(__file__).resolve().parent / "prompt_seed"

# slug -> (provider, schema dict)
_PROMPT_META: dict[str, tuple[str, dict[str, Any]]] = {
    "synthesizer": ("gateway", {"type": "object", "properties": {"context": {}, "user_message": {}}}),
    "intent_check": ("gateway", {"type": "object", "properties": {"message": {}}}),
    "query_refiner": ("gateway", {"type": "object", "properties": {"query": {}, "context": {}}}),
    "evidence_evaluator": ("gateway", {"type": "object", "properties": {"evidence": {}, "claim": {}}}),
    "structural_outline": ("gateway", {"type": "object", "properties": {"chunks": {}}}),
    "sandbox_prep": ("gateway", {"type": "object", "properties": {"expression": {}}}),
}


class PromptManager:
    async def ensure_seed_prompts(self) -> None:
        db = get_database()
        for slug, (provider, schema) in _PROMPT_META.items():
            path = _SEED_DIR / f"{slug}.jinja2"
            if not path.is_file():
                logger.warning("missing seed file %s", path)
                continue
            template = path.read_text(encoding="utf-8")
            await db.execute(
                """
                INSERT INTO prompts (slug, template, provider, schema)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (slug) DO NOTHING
                """,
                slug,
                template,
                provider,
                json.dumps(schema),
            )

    async def render(self, slug: str, variables: dict[str, Any]) -> str:
        db = get_database()
        row = await db.fetchrow("SELECT template FROM prompts WHERE slug = $1", slug)
        if not row:
            raise KeyError(f"unknown prompt slug: {slug}")
        tpl = _jinja.from_string(row["template"])
        return tpl.render(**variables)
