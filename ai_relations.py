"""AI: directed semantic relations and polarity from English source text."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from ai_preprocess import _chat_json, _openai_client
from graph import prune_graph_to_linked, submatrix, linked_label_set
from sign_scale import SCALE_PROMPT, resolve_edge_weight, strength_from_weight, strength_polarity_to_weight, weight_label

RELATION_SYSTEM_PROMPT = """You infer directed semantic relations between concept pairs using ONLY the provided English qualitative research text.

For each pair, concepts are given as (a, b) in alphabetical order. Return for each:
- direction:
  - "a_to_b" — the text supports A → B (A precedes, enables, leads to, or is prerequisite for B)
  - "b_to_a" — the text supports B → A
  - "mutual" — reciprocal / bidirectional link (A ↔ B)
- polarity:
  - "positive" — supportive, aligned, coherent association in context
  - "negative" — tension, opposition, trade-off, inhibition, or conflict between concepts
- strength:
  - "weak" — tentative or indirect link
  - "medium" — clear association in context
  - "strong" — dominant, explicit link in the text
- weight (optional): one of -1, -0.5, -0.25, 0.25, 0.5, 1 — if omitted, derived from strength + polarity

{scale_prompt}

Return JSON only:
{{"relations": [{{"a": "...", "b": "...", "direction": "a_to_b|b_to_a|mutual", "polarity": "positive|negative", "strength": "weak|medium|strong", "weight": <optional>}}]}}
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
_VALID_STRENGTH = frozenset({"weak", "medium", "strong"})
_RELATION_BATCH_SIZE = 24
_TEXT_MAX_CHARS = 80_000


def _canonical_pair(x: str, y: str) -> tuple[str, str]:
    return (x, y) if x <= y else (y, x)


def _relation_lookup_key(x: str, y: str) -> tuple[str, str]:
    a, b = x.strip().lower(), y.strip().lower()
    return (a, b) if a <= b else (b, a)


def _unique_pairs_from_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    pairs: list[dict[str, Any]] = []
    for e in edges:
        a, b = _canonical_pair(str(e["from"]), str(e["to"]))
        key = _relation_lookup_key(a, b)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"a": a, "b": b, "weight": float(e.get("weight", 0))})
    return pairs


def _parse_relations_json(
    data: dict[str, Any], pairs: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, str]]:
    raw = data.get("relations")
    if not isinstance(raw, list):
        raise ValueError("Relation response missing 'relations' array.")

    expected = {_relation_lookup_key(p["a"], p["b"]) for p in pairs}
    found: dict[tuple[str, str], dict[str, str]] = {}

    for item in raw:
        if not isinstance(item, dict):
            continue
        a_raw = str(item.get("a", "")).strip()
        b_raw = str(item.get("b", "")).strip()
        if not a_raw or not b_raw or a_raw.lower() == b_raw.lower():
            continue
        key = _relation_lookup_key(a_raw, b_raw)
        if key not in expected:
            continue
        direction = str(item.get("direction", "mutual")).strip().lower()
        polarity = str(item.get("polarity", "positive")).strip().lower()
        strength = str(item.get("strength", "medium")).strip().lower()
        if direction not in _VALID_DIRECTIONS:
            direction = "mutual"
        if polarity not in _VALID_POLARITIES:
            polarity = "positive"
        if strength not in _VALID_STRENGTH:
            strength = "medium"
        weight = resolve_edge_weight(
            item.get("weight"), strength=strength, polarity=polarity
        )
        found[key] = {
            "direction": direction,
            "polarity": polarity,
            "strength": strength,
            "weight": weight,
        }

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
        system=RELATION_SYSTEM_PROMPT.format(scale_prompt=SCALE_PROMPT),
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

    defaults = {
        "direction": "mutual",
        "polarity": "positive",
        "strength": "medium",
        "weight": strength_polarity_to_weight("medium", "positive"),
    }
    for p in pairs:
        key = _relation_lookup_key(p["a"], p["b"])
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

        rel = relations.get(
            _relation_lookup_key(a, b),
            {
                "direction": "mutual",
                "polarity": "positive",
                "strength": "medium",
                "weight": strength_polarity_to_weight("medium", "positive"),
            },
        )
        direction = rel["direction"]
        polarity = rel["polarity"]
        strength = rel.get("strength", "medium")
        signed = float(
            rel.get("weight")
            or resolve_edge_weight(None, strength=strength, polarity=polarity)
        )
        strength = strength_from_weight(signed)
        label = weight_label(signed)

        def _edge(frm: str, to: str, dir_label: str) -> dict[str, Any]:
            return {
                "from": frm,
                "to": to,
                "weight": abs(signed),
                "signed_weight": signed,
                "polarity": polarity,
                "strength": strength,
                "weight_label": label,
                "direction": dir_label,
                "value": e.get("value", 1),
                "title": (
                    f"{frm} → {to}: {signed:+.2f} ({label or polarity}, "
                    f"{dir_label.replace('_', ' ')})"
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
    on_progress=None,
    progress_ctx: dict | None = None,
) -> dict[str, dict[str, Any]]:
    from workflow import RELATION_STEP_BY_KIND, emit

    oai = client or _openai_client(api_key=api_key, base_url=base_url)
    chosen_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    enriched: dict[str, dict[str, Any]] = {}

    for kind, graph in graphs.items():
        step_id = RELATION_STEP_BY_KIND.get(kind, f"relations_{kind}")
        pairs = _unique_pairs_from_edges(graph.get("edges") or [])
        emit(
            on_progress,
            step_id,
            "running",
            {**(progress_ctx or {}), "kind": kind, "pairs": len(pairs)},
        )
        relations = infer_relations_for_pairs(
            english_text,
            pairs,
            kind,
            client=oai,
            model=chosen_model,
        )
        enriched[kind] = prune_graph_to_linked(
            apply_relations_to_graph(graph, relations)
        )
        emit(
            on_progress,
            step_id,
            "done",
            {**(progress_ctx or {}), "kind": kind, "pairs": len(pairs)},
        )

    return enriched


def matrices_from_directed_graphs(
    graphs: dict[str, dict[str, Any]],
    labels_by_kind: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for kind, graph in graphs.items():
        if kind not in labels_by_kind:
            continue
        edges = graph.get("edges") or []
        all_labels = labels_by_kind[kind]
        linked = linked_label_set(edges)
        keep = [lab for lab in all_labels if lab in linked]
        if not keep:
            result[kind] = {"labels": [], "values": []}
            continue
        full = directed_matrix_from_edges(all_labels, edges)
        if len(keep) < len(all_labels):
            result[kind] = submatrix(all_labels, full["values"], keep)
        else:
            result[kind] = full
    return result
