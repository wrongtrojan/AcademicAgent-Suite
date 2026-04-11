"""Central logging setup: one format, env-driven level, optional rotating log files."""

from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

# Single file max before rotate (bytes)
_LOG_FILE_MAX_BYTES = int(os.environ.get("LOG_FILE_MAX_BYTES", str(20 * 1024 * 1024)))
_LOG_FILE_BACKUP_COUNT = int(os.environ.get("LOG_FILE_BACKUP_COUNT", "5"))


def _safe_log_filename(label: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", label.strip() or "app")
    return f"{s}.log"


def setup_logging(service_name: str | None = None) -> None:
    """
    Configure root logging once. Idempotent per process.

    Env:
      LOG_LEVEL — DEBUG, INFO, WARNING, ERROR (default INFO)
      LOG_SERVICE — optional; overrides service_name for the line prefix and log file stem
      LOG_DIR — if set, also write RotatingFileHandler under this directory (e.g. /var/log/contextmap)
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    label = os.environ.get("LOG_SERVICE") or service_name or "app"

    fmt = logging.Formatter(
        fmt=f"%(asctime)s | %(levelname)-8s | {label} | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    root.addHandler(stdout_handler)

    log_dir = os.environ.get("LOG_DIR", "").strip()
    if log_dir:
        path = Path(log_dir)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / _safe_log_filename(label)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=_LOG_FILE_MAX_BYTES,
            backupCount=_LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # Third-party noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    _CONFIGURED = True
