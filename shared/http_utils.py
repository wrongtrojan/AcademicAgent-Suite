from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from shared.url_policy import assert_fetch_url_allowed


def rewrite_localhost_gateway_url(url: str) -> str:
    """
    Gateway may register file URLs with http://localhost:8000 for browsers on the host.
    Workers run in other containers and must fetch via the gateway service name (e.g. http://gateway:8000).
    Set GATEWAY_INTERNAL_ORIGIN=http://gateway:8000 in Compose for pipeline workers.
    """
    internal = os.environ.get("GATEWAY_INTERNAL_ORIGIN", "").strip().rstrip("/")
    if not internal:
        return url
    for prefix in ("http://127.0.0.1:8000", "http://localhost:8000"):
        if url.startswith(prefix):
            return internal + url[len(prefix) :]
    return url


async def fetch_url_bytes(url: str) -> bytes:
    url = rewrite_localhost_gateway_url(url)
    assert_fetch_url_allowed(url)
    parsed = urlparse(url)
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path))
        return path.read_bytes()
    if parsed.scheme in ("http", "https"):
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content
    raise ValueError(f"Unsupported URL scheme for fetch: {parsed.scheme}")
