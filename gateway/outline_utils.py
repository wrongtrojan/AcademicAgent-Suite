"""Map DB `structure_outline` JSON to the shape expected by the Next app (OutlineItem / sub_points)."""

from __future__ import annotations

from typing import Any


def outline_children_flat(nodes: list | None, depth: int = 0) -> list[dict[str, Any]]:
    """Flatten nested `children` into a list of {heading, anchor, summary} for one UI level."""
    res: list[dict[str, Any]] = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        title = (n.get("title") or n.get("heading") or "").strip()
        if depth and title:
            title = ("  " * depth) + title
        res.append(
            {
                "heading": title,
                "anchor": float(n.get("anchor", 1)),
                "summary": (n.get("summary") or "").strip(),
            }
        )
        deeper = n.get("children") or n.get("sub_points")
        if isinstance(deeper, list) and deeper:
            res.extend(outline_children_flat(deeper, depth + 1))
    return res


def outline_to_frontend(db_outline: list | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in db_outline or []:
        if not isinstance(node, dict):
            continue
        sub_raw = node.get("children") or node.get("sub_points") or []
        out.append(
            {
                "heading": (node.get("title") or node.get("heading") or "").strip(),
                "anchor": float(node.get("anchor", 1)),
                "summary": (node.get("summary") or "").strip(),
                "sub_points": outline_children_flat(sub_raw, depth=0),
            }
        )
    return out
