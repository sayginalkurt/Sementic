"""FCM adjacency matrix and graph from directed edges."""

from __future__ import annotations

from typing import Any


def adjacency_from_edges(
    concepts: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Square adjacency matrix: rows = source, cols = target."""
    labels = [c["label"] for c in concepts]
    n = len(labels)
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
    labels = [c["label"] for c in concepts]
    degree: dict[str, float] = {lab: 0.0 for lab in labels}

    for e in edges:
        w = abs(float(e.get("weight", 0)))
        degree[e["source"]] = degree.get(e["source"], 0) + w
        degree[e["target"]] = degree.get(e["target"], 0) + w

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

    max_w = max((abs(int(e.get("weight", 1))) for e in edges), default=2)
    vis_edges = []
    for e in edges:
        w = int(e.get("weight", 0))
        polarity = "positive" if w > 0 else "negative"
        vis_edges.append(
            {
                "from": e["source"],
                "to": e["target"],
                "weight": abs(w),
                "signed_weight": float(w),
                "value": 1 + (abs(w) / max_w) * 6,
                "polarity": polarity,
                "direction": "a_to_b",
                "strength": e.get("strength", "medium"),
                "evidence_sentence": e.get("evidence_sentence", ""),
                "analyst_note": e.get("analyst_note", ""),
                "title": (
                    f"{e['source']} → {e['target']}: {w:+d}\n"
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
