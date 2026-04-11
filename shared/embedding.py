"""Text embeddings: hash fallback (dev) or BGE-M3 via sentence-transformers (EMBEDDING_BACKEND=bge).

EMBEDDING_DEVICE (optional): e.g. cuda, cpu, cuda:0 — passed to SentenceTransformer when set; unset keeps library default.
"""

from __future__ import annotations

import hashlib
import logging
import os
from functools import lru_cache
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)


def _embed_hash(text: str, dim: int = 128) -> np.ndarray:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(h[:8], "big")
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    n = float(np.linalg.norm(v)) or 1.0
    return v / n


def _embedding_device_key() -> str:
    """Empty string = let sentence-transformers pick device (legacy auto). Otherwise e.g. cuda, cpu, cuda:0."""
    return os.environ.get("EMBEDDING_DEVICE", "").strip()


@lru_cache(maxsize=8)
def _sentence_transformer(model_id: str, device_key: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "EMBEDDING_BACKEND=bge requires sentence-transformers. "
            "Install: pip install sentence-transformers torch"
        ) from exc
    dev = device_key or None
    logger.info("Loading embedding model %s device=%s", model_id, dev or "auto")
    if dev:
        return SentenceTransformer(model_id, device=dev)
    return SentenceTransformer(model_id)


def _load_sentence_transformer():
    model_id = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
    return _sentence_transformer(model_id, _embedding_device_key())


def embed_text(text: str, dim: int = 128) -> np.ndarray:
    """
    Embed a single text. Backend from EMBEDDING_BACKEND (hash | bge).
    Hash uses fixed dim; BGE-M3 dimension follows the model (typically 1024).
    """
    backend = os.environ.get("EMBEDDING_BACKEND", "hash").lower().strip()
    if backend == "bge":
        model = _load_sentence_transformer()
        v = model.encode(text or "", normalize_embeddings=True)
        arr = np.asarray(v, dtype=np.float32).reshape(-1)
        return arr
    return _embed_hash(text, dim=dim)


def embedding_dim() -> int:
    """Return dimension for dense_embedding column (hint for migrations)."""
    if os.environ.get("EMBEDDING_BACKEND", "hash").lower() == "bge":
        return int(os.environ.get("EMBEDDING_DIM", "1024"))
    return int(os.environ.get("EMBEDDING_DIM", "128"))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    aa = np.array(a, dtype=np.float32)
    bb = np.array(b, dtype=np.float32)
    if aa.size == 0 or bb.size == 0:
        return 0.0
    if aa.shape != bb.shape:
        return 0.0
    denom = float(np.linalg.norm(aa) * np.linalg.norm(bb)) or 1.0
    return float(np.dot(aa, bb) / denom)
