"""FCM adjacency matrix and graph from directed edges."""

from __future__ import annotations

from typing import Any

from graph import linked_label_set
from sign_scale import weight_label


def _linked_labels(concepts: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    linked = linked_label_set(edges, src_key="source", tgt_key="target")
    return [c["label"] for c in concepts if c["label"] in linked]


def adjacency_from_edges(
    concepts: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Square adjacency matrix: rows = source, cols = target."""
    labels = _linked_labels(concepts, edges)
    n = len(labels)
    if not n:
        return {"labels": [], "values": []}

    idx = {lab: i for i, lab in enumerate(labels)}
    values = [[0.0] * n for _ in range(n)]

    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src not in idx or tgt not in idx:
            continue
        values[idx[src]][idx[tgt]] = float(e.get("weight", 0))

    return {"labels": labels, "values": values}


def fcm_graph_from_edges(
    concepts: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """vis-network compatible directed FCM graph."""
    labels = _linked_labels(concepts, edges)
    if not labels:
        return {
            "nodes": [],
            "edges": [],
            "stats": {"node_count": 0, "edge_count": 0, "kind": "fcm"},
        }

    degree: dict[str, float] = {lab: 0.0 for lab in labels}

    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src not in degree or tgt not in degree:
            continue
        w = abs(float(e.get("weight", 0)))
        degree[src] = degree.get(src, 0) + w
        degree[tgt] = degree.get(tgt, 0) + w

    max_deg = max(degree.values()) if degree else 1.0
    nodes = [
        {
            "id": lab,
            "label": lab,
            "value": 10 + (degree.get(lab, 0) / max_deg) * 20 if max_deg else 12,
            "title": f"{lab}\nInfluence degree: {degree.get(lab, 0):.1f}",
        }
        for lab in labels
    ]

    vis_edges = []
    max_w = max((abs(float(e.get("weight", 0))) for e in edges), default=1.0)
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src not in degree or tgt not in degree:
            continue
        w = float(e.get("weight", 0))
        polarity = "positive" if w > 0 else "negative"
        label = weight_label(w)
        vis_edges.append(
            {
                "from": src,
                "to": tgt,
                "weight": abs(w),
                "signed_weight": w,
                "value": 1 + (abs(w) / max_w) * 6,
                "polarity": polarity,
                "direction": "a_to_b",
                "strength": e.get("strength", "medium"),
                "weight_label": label,
                "evidence_sentence": e.get("evidence_sentence", ""),
                "analyst_note": e.get("analyst_note", ""),
                "title": (
                    f"{src} → {tgt}: {w:+.2f} ({label})\n"
                    f"{e.get('analyst_note', '')}"
                ),
            }
        )

    return {
        "nodes": nodes,
        "edges": vis_edges,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(vis_edges),
            "kind": "fcm",
        },
    }
