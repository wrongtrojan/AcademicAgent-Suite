"""MinerU / magic-pdf: try Python module API, then `python -m mineru`, then magic-pdf CLI."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _has_extracted_files(out_dir: Path) -> bool:
    for p in out_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in (".md", ".json", ".txt") and "manifest" not in p.name.lower():
            return True
    return False


def run_mineru_extract(pdf_path: Path, out_dir: Path) -> bool:
    """
    Run OCR / layout extraction into out_dir.
    Controlled by MINERU_MODE: auto | api | module | cli | skip | synthetic
    """
    mode = os.environ.get("MINERU_MODE", "auto").lower().strip()
    if mode in ("skip", "synthetic", "none"):
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    timeout = int(os.environ.get("MINERU_TIMEOUT", "3600"))

    # Optional in-process hook: MINERU_PYTHON_ENTRY=my.pkg:run_pdf
    entry = os.environ.get("MINERU_PYTHON_ENTRY", "").strip()
    if entry and mode in ("auto", "api", "python"):
        try:
            mod_name, _, func_name = entry.partition(":")
            if not func_name:
                raise ValueError("MINERU_PYTHON_ENTRY must be like package.module:function")
            import importlib

            mod = importlib.import_module(mod_name)
            fn = getattr(mod, func_name)
            fn(str(pdf_path), str(out_dir))
            if _has_extracted_files(out_dir):
                logger.info("MinerU MINERU_PYTHON_ENTRY produced output")
                return True
        except Exception as exc:
            logger.warning("MINERU_PYTHON_ENTRY failed: %s", exc)

    # python -m mineru (OpenDataLab MinerU typical CLI)
    if mode in ("auto", "api", "module"):
        try:
            subprocess.run(
                [sys.executable, "-m", "mineru", "-p", str(pdf_path), "-o", str(out_dir)],
                check=True,
                cwd=str(out_dir.parent),
                timeout=timeout,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            if _has_extracted_files(out_dir):
                logger.info("python -m mineru produced output")
                return True
        except FileNotFoundError:
            logger.debug("mineru package not available")
        except subprocess.CalledProcessError as exc:
            logger.warning("python -m mineru exited %s", exc.returncode)
        except Exception as exc:
            logger.warning("python -m mineru failed: %s", exc)

    # magic-pdf / mineru executable on PATH
    if mode in ("auto", "cli"):
        exe = os.environ.get("MAGIC_PDF_BIN") or shutil.which("magic-pdf")
        if exe:
            try:
                subprocess.run(
                    [exe, "pdf", "--pdf", str(pdf_path), "--method", "ocr"],
                    check=True,
                    cwd=str(out_dir),
                    timeout=timeout,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
                if _has_extracted_files(out_dir):
                    logger.info("magic-pdf produced output")
                    return True
            except Exception as exc:
                logger.warning("magic-pdf failed: %s", exc)

        mineru_bin = shutil.which("mineru")
        if mineru_bin:
            try:
                subprocess.run(
                    [mineru_bin, "-p", str(pdf_path), "-o", str(out_dir)],
                    check=True,
                    cwd=str(out_dir),
                    timeout=timeout,
                )
                if _has_extracted_files(out_dir):
                    logger.info("mineru binary produced output")
                    return True
            except Exception as exc:
                logger.warning("mineru binary failed: %s", exc)

    return False
