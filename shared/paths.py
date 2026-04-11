from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


def storage_root() -> Path:
    return Path(os.environ.get("STORAGE_ROOT", "./storage")).resolve()


def url_to_storage_path(url: str) -> Path:
    """Map gateway static URL or file:// URL to absolute storage path."""
    if url.startswith("file://"):
        p = urlparse(url)
        return Path(unquote(p.path))
    marker = "/static/storage/"
    if marker in url:
        rel = url.split(marker, 1)[1]
        return storage_root() / rel
    raise ValueError(f"Cannot map URL to storage path: {url}")
