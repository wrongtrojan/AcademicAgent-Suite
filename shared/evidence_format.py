"""Build frontend `Evidence.metadata` from chunk coordination + asset type (see frontend/lib/types.ts)."""

from __future__ import annotations

import json
from typing import Any


def evidence_metadata_for_chunk(
    coordination: Any,
    asset_type: str,
    asset_id: str,
) -> dict[str, Any]:
    """
    `asset_name` is the asset UUID string so it matches `normalizeAsset` / AssetCard lookup.
    """
    coord = coordination if isinstance(coordination, dict) else {}
    modality: Any = "video" if (asset_type or "").lower() == "video" else "pdf"
    meta: dict[str, Any] = {
        "asset_name": str(asset_id),
        "modality": modality,
    }
    if modality == "pdf":
        pg = coord.get("page")
        if pg is not None:
            try:
                meta["page_label"] = int(float(pg))
            except (TypeError, ValueError):
                meta["page_label"] = 1
        bbox = coord.get("bbox")
        if bbox is not None:
            meta["bbox"] = json.dumps(bbox) if not isinstance(bbox, str) else bbox
    else:
        for key in ("timestamp_start", "timestamp", "t", "time"):
            ts = coord.get(key)
            if ts is not None:
                try:
                    meta["timestamp"] = float(ts)
                except (TypeError, ValueError):
                    pass
                break
    return meta


def hit_to_evidence(hit: dict[str, Any]) -> dict[str, Any]:
    """Shape one hybrid_search hit as an `Evidence` object for the frontend."""
    meta = hit.get("metadata") or {}
    return {
        "content": (hit.get("content") or "")[:2000],
        "score": float(hit.get("score") or 0.0),
        "metadata": meta,
    }
