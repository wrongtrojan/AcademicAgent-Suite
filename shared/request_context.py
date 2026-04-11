"""Request-scoped context (e.g. correlation id) for HTTP handlers."""

from __future__ import annotations

import contextvars

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_var.get()
