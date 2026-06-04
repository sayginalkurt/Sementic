"""AI: directed semantic relations and polarity from English source text."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from ai_preprocess import _chat_json, _openai_client

RELATION_SYSTEM_PROMPT = """You infer directed semantic relations between concept pairs using ONLY the provided English qualitative research text.

For each pair, concepts are given as (a, b) in alphabetical order. Return for each:
- direction:
  - "a_to_b" — the text supports A → B (A precedes, enables, leads to, or is prerequisite for B)
  - "b_to_a" — the text supports B → A
  - "mutual" — reciprocal / bidirectional link (A ↔ B)
- polarity:
  - "positive" — supportive, aligned, coherent association in context
  - "negative" — tension, opposition, trade-off, inhibition, or conflict between concepts

Return JSON only:
{"relations": [{"a": "...", "b": "...", "direction": "a_to_b|b_to_a|mutual", "polarity": "positive|negative"}]}
Use exact concept strings from the input. One object per pair listed."""

RELATION_USER_TEMPLATE = """Analysis type: {kind}
Context: {kind_note}

English text:
---
{text}
---

Concept pairs to label (alphabetical a, b):
{pairs_json}"""

KIND_NOTES = {
    "cooccurrence": "Pairs co-occur in the same sentence; infer causal or logical direction from discourse, not just proximity.",
    "semantic": "Pairs are distributionally similar; infer how meanings relate directionally in the argument.",
    "epistemic": "ENA-style association; infer epistemic flow (what supports or constrains what).",
}

_VALID_DIRECTIONS = frozenset({"a_to_b", "b_to_a", "mutual"})
_VALID_POLARITIES = frozenset({"positive", "negative"})
_RELATION_BATCH_SIZE = 24
_TEXT_MAX_CHARS = 80_000


def _canonical_pair(x: str, y: str) -> tuple[str, str]:
    return (x, y) if x <= y else (y, x)


def _unique_pairs_from_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    pairs: list[dict[str, Any]] = []
    for e in edges:
        a, b = _canonical_pair(str(e["from"]), str(e["to"]))
        if (a, b) in seen:
            continue
        seen.add((a, b))
        pairs.append({"a": a, "b": b, "weight": float(e.get("weight", 0))})
    return pairs


def _parse_relations_json(
    data: dict[str, Any], pairs: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, str]]:
    raw = data.get("relations")
    if not isinstance(raw, list):
        raise ValueError("Relation response missing 'relations' array.")

    expected = {_canonical_pair(p["a"], p["b"]) for p in pairs}
    found: dict[tuple[str, str], dict[str, str]] = {}

    for item in raw:
        if not isinstance(item, dict):
            continue
        a = str(item.get("a", "")).strip().lower()
        b = str(item.get("b", "")).strip().lower()
        if not a or not b or a == b:
            continue
        key = _canonical_pair(a, b)
        if key not in expected:
            continue
        direction = str(item.get("direction", "mutual")).strip().lower()
        polarity = str(item.get("polarity", "positive")).strip().lower()
        if direction not in _VALID_DIRECTIONS:
            direction = "mutual"
        if polarity not in _VALID_POLARITIES:
            polarity = "positive"
        found[key] = {"direction": direction, "polarity": polarity}

    return found


def _infer_relations_batch(
    client: OpenAI,
    model: str,
    *,
    kind: str,
    english_text: str,
    pairs: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, str]]:
    if not pairs:
        return {}

    data = _chat_json(
        client,
        model,
        system=RELATION_SYSTEM_PROMPT,
        user=RELATION_USER_TEMPLATE.format(
            kind=kind,
            kind_note=KIND_NOTES.get(kind, KIND_NOTES["cooccurrence"]),
            text=english_text[:_TEXT_MAX_CHARS],
            pairs_json=json.dumps(
                [{"a": p["a"], "b": p["b"]} for p in pairs], ensure_ascii=False
            ),
        ),
    )
    return _parse_relations_json(data, pairs)


def infer_relations_for_pairs(
    english_text: str,
    pairs: list[dict[str, Any]],
    kind: str,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[tuple[str, str], dict[str, str]]:
    """Map (a,b) → {direction, polarity}; default mutual/positive when missing."""
    if not pairs:
        return {}

    chosen_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    oai = client or _openai_client(api_key=api_key, base_url=base_url)

    merged: dict[tuple[str, str], dict[str, str]] = {}
    for i in range(0, len(pairs), _RELATION_BATCH_SIZE):
        batch = pairs[i : i + _RELATION_BATCH_SIZE]
        try:
            merged.update(
                _infer_relations_batch(
                    oai, chosen_model, kind=kind, english_text=english_text, pairs=batch
                )
            )
        except (ValueError, json.JSONDecodeError):
            continue

    defaults = {"direction": "mutual", "polarity": "positive"}
    for p in pairs:
        key = _canonical_pair(p["a"], p["b"])
        merged.setdefault(key, dict(defaults))
    return merged


def _directed_edges(
    base_edges: list[dict[str, Any]],
    relations: dict[tuple[str, str], dict[str, str]],
) -> list[dict[str, Any]]:
    """Expand undirected edge specs into directed, signed edges."""
    out: list[dict[str, Any]] = []
    seen_pair: set[tuple[str, str]] = set()

    for e in base_edges:
        a, b = _canonical_pair(str(e["from"]), str(e["to"]))
        if (a, b) in seen_pair:
            continue
        seen_pair.add((a, b))

        rel = relations.get((a, b), {"direction": "mutual", "polarity": "positive"})
        direction = rel["direction"]
        polarity = rel["polarity"]
        sign = -1.0 if polarity == "negative" else 1.0
        w = float(e.get("weight", 0))
        signed = w * sign

        def _edge(frm: str, to: str, dir_label: str) -> dict[str, Any]:
            return {
                "from": frm,
                "to": to,
                "weight": w,
                "signed_weight": signed,
                "polarity": polarity,
                "direction": dir_label,
                "value": e.get("value", 1),
                "title": (
                    f"{frm} → {to}: {signed:+.3f} "
                    f"({polarity}, {dir_label.replace('_', ' ')})"
                ),
            }

        if direction == "a_to_b":
            out.append(_edge(a, b, "a_to_b"))
        elif direction == "b_to_a":
            out.append(_edge(b, a, "b_to_a"))
        else:
            out.append(_edge(a, b, "mutual"))
            out.append(_edge(b, a, "mutual"))

    return out


def apply_relations_to_graph(
    graph: dict[str, Any],
    relations: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    """Rebuild nodes/edges with directed signed semantics."""
    base_edges = graph.get("edges") or []
    directed = _directed_edges(base_edges, relations)

    degree: dict[str, float] = {n["id"]: 0.0 for n in graph.get("nodes", [])}
    for e in directed:
        degree[e["from"]] = degree.get(e["from"], 0) + abs(e["signed_weight"])
        degree[e["to"]] = degree.get(e["to"], 0) + abs(e["signed_weight"])

    max_deg = max(degree.values()) if degree else 1.0
    nodes = []
    for n in graph.get("nodes", []):
        lab = n["id"]
        deg = degree.get(lab, 0)
        nodes.append(
            {
                **n,
                "value": 8 + (deg / max_deg) * 22 if max_deg else 12,
                "title": f"{lab}\nConnection weight: {deg:.2f}",
            }
        )

    max_w = max((abs(e["signed_weight"]) for e in directed), default=1.0)
    edges = []
    for e in directed:
        sw = e["signed_weight"]
        edges.append(
            {
                **e,
                "value": 1 + (abs(sw) / max_w) * 8 if max_w else 1,
            }
        )

    stats = dict(graph.get("stats") or {})
    stats["edge_count"] = len(edges)
    return {"nodes": nodes, "edges": edges, "stats": stats}


def directed_matrix_from_edges(
    labels: list[str], edges: list[dict[str, Any]]
) -> dict[str, Any]:
    """Asymmetric signed matrix from directed edges (no self-loops)."""
    n = len(labels)
    idx = {lab: i for i, lab in enumerate(labels)}
    values = [[0.0] * n for _ in range(n)]
    for e in edges:
        frm, to = e["from"], e["to"]
        if frm not in idx or to not in idx or frm == to:
            continue
        values[idx[frm]][idx[to]] = float(e.get("signed_weight", e.get("weight", 0)))
    return {"labels": labels, "values": values}


def annotate_graphs_with_relations(
    graphs: dict[str, dict[str, Any]],
    english_text: str,
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, dict[str, Any]]:
    oai = client or _openai_client(api_key=api_key, base_url=base_url)
    chosen_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    enriched: dict[str, dict[str, Any]] = {}

    for kind, graph in graphs.items():
        pairs = _unique_pairs_from_edges(graph.get("edges") or [])
        relations = infer_relations_for_pairs(
            english_text,
            pairs,
            kind,
            client=oai,
            model=chosen_model,
        )
        enriched[kind] = apply_relations_to_graph(graph, relations)

    return enriched


def matrices_from_directed_graphs(
    graphs: dict[str, dict[str, Any]],
    labels_by_kind: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    return {
        kind: directed_matrix_from_edges(
            labels_by_kind[kind], graphs[kind].get("edges") or []
        )
        for kind in graphs
        if kind in labels_by_kind
    }
