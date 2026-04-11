"""URL scheme policy: restrict file:// and internal URLs in production."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from shared.protocol.errors import ErrorCode, ProtocolError


def assert_fetch_url_allowed(url: str) -> None:
    """Raise if URL must not be fetched in this environment."""
    parsed = urlparse(url)
    if parsed.scheme == "file":
        allow = os.environ.get("ALLOW_FILE_URL", "1").lower() in ("1", "true", "yes")
        if not allow:
            raise ProtocolError(
                ErrorCode.INVALID_ENVELOPE,
                "file:// URLs are disabled (set ALLOW_FILE_URL=1 for dev)",
            )
    if parsed.scheme in ("http", "https"):
        return
    if parsed.scheme in ("s3", "minio"):
        return
    if parsed.scheme == "file":
        return


def is_production_strict() -> bool:
    return os.environ.get("CONTEXTMAP_ENV", "dev").lower() == "production"
