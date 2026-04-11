from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from compiler.parser import load_workflow


class ChatTurnState(TypedDict, total=False):
    session_id: str
    user_message: str
    context: str
    answer: str


def compile_chat_turn_graph(
    retrieve_fn: Callable[..., Any],
    synthesize_fn: Callable[..., Any],
    dsl_path: str | Path | None = None,
):
    """Backward-compatible: fixed retrieve/synthesize graph."""
    if dsl_path is not None:
        load_workflow(dsl_path)
    g = StateGraph(ChatTurnState)
    g.add_node("retrieve", retrieve_fn)
    g.add_node("synthesize", synthesize_fn)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()


def build_workflow_from_dsl(
    dsl_path: str | Path,
    state_cls: type,
    node_handlers: dict[str, Callable[..., Any]],
):
    """
    Build a LangGraph from DSL: nodes + edges in YAML.
    Terminal nodes (no outgoing edge) are connected to END.
    """
    spec = load_workflow(dsl_path)
    entry = spec.get("entry")
    nodes_spec = spec.get("nodes") or {}
    edges = spec.get("edges") or []
    if not entry or entry not in nodes_spec:
        raise ValueError("DSL must define entry and nodes")
    for nid in nodes_spec:
        if nid not in node_handlers:
            raise KeyError(f"No handler registered for node '{nid}'")

    g = StateGraph(state_cls)
    for nid in nodes_spec:
        g.add_node(nid, node_handlers[nid])
    g.set_entry_point(entry)

    if not edges:
        g.add_edge(entry, END)
        return g.compile()

    from_ids = {e["from"] for e in edges}
    for e in edges:
        g.add_edge(e["from"], e["to"])

    for nid in nodes_spec:
        if nid not in from_ids:
            g.add_edge(nid, END)

    return g.compile()
