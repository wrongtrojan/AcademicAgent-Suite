"""
ASGI middleware: one clear line per HTTP request (method, path, status, duration, request_id).
Does not use BaseHTTPMiddleware so streaming (SSE) stays correct.
"""

from __future__ import annotations

import logging
import os
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shared.request_context import request_id_var

logger = logging.getLogger("gateway.http")

# Comma-separated path prefixes to omit from INFO logs (e.g. noisy health probes).
# Example: CONTEXTMAP_LOG_HTTP_SKIP_PREFIXES=/api/v1/health
_SKIP_PREFIXES: tuple[str, ...] = tuple(
    p.strip()
    for p in os.environ.get("CONTEXTMAP_LOG_HTTP_SKIP_PREFIXES", "").split(",")
    if p.strip()
)


def _get_header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers") or []:
        if k.lower() == name.lower():
            try:
                return v.decode("latin-1")
            except Exception:
                return None
    return None


def _should_skip_log(scope: Scope) -> bool:
    if scope["type"] != "http":
        return True
    path = scope.get("path") or ""
    return any(path.startswith(p) for p in _SKIP_PREFIXES)


class HttpRequestLoggingMiddleware:
    """Logs each request when the response completes (including streamed bodies)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid_in = _get_header(scope, b"x-request-id")
        request_id = rid_in.strip() if rid_in else str(uuid.uuid4())

        method = scope.get("method", "?")
        path = scope.get("path", "")
        client = "?"
        if scope.get("client"):
            client = f"{scope['client'][0]}:{scope['client'][1]}"

        skip = _should_skip_log(scope)
        t0 = time.perf_counter()
        status_code: int | None = None

        token = request_id_var.set(request_id)
        logged_exc = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers") or [])
                names = {h[0].lower() for h in headers}
                rid_bytes = request_id.encode("latin-1")
                if b"x-request-id" not in names:
                    headers.append((b"x-request-id", rid_bytes))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logged_exc = True
            if not skip:
                logger.exception(
                    "http | %s %s | error | client=%s | request_id=%s",
                    method,
                    path,
                    client,
                    request_id,
                )
            raise
        finally:
            request_id_var.reset(token)
            if not skip and not logged_exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                code = status_code if status_code is not None else 0
                logger.info(
                    "http | %s %s | %s | %.2fms | client=%s | request_id=%s",
                    method,
                    path,
                    code,
                    elapsed_ms,
                    client,
                    request_id,
                )
