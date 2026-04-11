"""Optional steps between retrieval and synthesis (sandbox / visual — extend with broker calls)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def post_retrieve_hooks(state: dict[str, Any]) -> dict[str, Any]:
    """
    Placeholder for README「增强验证」:
    - Science sandbox: publish to `sandbox_inference` via Redis when implemented.
    - Visual: publish to `visual_inference` when `VISUAL_USE_VLM` + API keys are set.

    Today this is a no-op pass-through so the LangGraph slot exists without blocking chat.
    """
    if os.environ.get("CONTEXTMAP_LOG_CHAT_HOOKS", "").lower() in ("1", "true", "yes"):
        logger.info("post_retrieve_hooks (no-op); set CONTEXTMAP_ENABLE_* to extend")
    return {**state}
