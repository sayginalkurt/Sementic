"""Matris → node/edge ağ yapısı (web görselleştirme)."""

from __future__ import annotations

from typing import Any


def linked_label_set(
    edges: list[dict[str, Any]],
    *,
    src_key: str = "from",
    tgt_key: str = "to",
) -> set[str]:
    linked: set[str] = set()
    for e in edges:
        src = e.get(src_key)
        tgt = e.get(tgt_key)
        if src:
            linked.add(str(src))
        if tgt:
            linked.add(str(tgt))
    return linked


def submatrix(labels: list[str], values: list[list[float]], keep: list[str]) -> dict[str, Any]:
    if not keep:
        return {"labels": [], "values": []}
    idx = {lab: i for i, lab in enumerate(labels)}
    n = len(keep)
    out = [[0.0] * n for _ in range(n)]
    for i, li in enumerate(keep):
        for j, lj in enumerate(keep):
            out[i][j] = float(values[idx[li]][idx[lj]])
    return {"labels": keep, "values": out}


def prune_graph_to_linked(graph: dict[str, Any]) -> dict[str, Any]:
    """Drop nodes (and matrix rows/cols) that have no edge in this graph."""
    edges = list(graph.get("edges") or [])
    linked = linked_label_set(edges)
    if not linked:
        stats = dict(graph.get("stats") or {})
        stats.update(node_count=0, edge_count=0)
        return {"nodes": [], "edges": [], "stats": stats}

    nodes = [n for n in (graph.get("nodes") or []) if n.get("id") in linked]
    stats = dict(graph.get("stats") or {})
    stats["node_count"] = len(nodes)
    stats["edge_count"] = len(edges)
    return {"nodes": nodes, "edges": edges, "stats": stats}


def _off_diagonal_pairs(labels: list[str], values: list[list[float]]) -> list[tuple[int, int, float]]:
    n = len(labels)
    pairs: list[tuple[int, int, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((i, j, float(values[i][j])))
    return pairs


def _percentile_threshold(nums: list[float], q: float = 0.55) -> float:
    if not nums:
        return 0.0
    sorted_nums = sorted(nums)
    idx = min(int(len(sorted_nums) * q), len(sorted_nums) - 1)
    return sorted_nums[max(0, idx)]


def matrix_to_graph(
    labels: list[str],
    values: list[list[float]],
    kind: str,
) -> dict[str, Any]:
    """
    Matristen görselleştirme grafiği üretir.
    kind: cooccurrence | semantic | epistemic
    """
    pairs = _off_diagonal_pairs(labels, values)
    edge_specs: list[dict[str, Any]] = []

    if kind == "cooccurrence":
        for i, j, w in pairs:
            if w > 0:
                edge_specs.append(
                    {"from": labels[i], "to": labels[j], "weight": w, "polarity": "neutral"}
                )

    elif kind == "semantic":
        candidates = [(i, j, w) for i, j, w in pairs if w > 0.05]
        candidates.sort(key=lambda x: -x[2])
        cap = max(25, min(len(candidates), len(labels) * 3))
        thresh = _percentile_threshold([w for _, _, w in candidates], 0.5)
        for i, j, w in candidates[:cap]:
            if w >= thresh:
                edge_specs.append(
                    {"from": labels[i], "to": labels[j], "weight": w, "polarity": "neutral"}
                )

    elif kind == "epistemic":
        abs_vals = [abs(w) for _, _, w in pairs if abs(w) > 1e-9]
        thresh = _percentile_threshold(abs_vals, 0.55) if abs_vals else 0.0
        for i, j, w in pairs:
            if abs(w) >= thresh and abs(w) > 1e-9:
                edge_specs.append(
                    {
                        "from": labels[i],
                        "to": labels[j],
                        "weight": abs(w),
                        "polarity": "neutral",
                    }
                )
    else:
        raise ValueError(f"Bilinmeyen graf türü: {kind}")

    degree: dict[str, float] = {lab: 0.0 for lab in labels}
    for e in edge_specs:
        degree[e["from"]] += e["weight"]
        degree[e["to"]] += e["weight"]

    max_deg = max(degree.values()) if degree else 1.0
    nodes = [
        {
            "id": lab,
            "label": lab,
            "value": 8 + (degree[lab] / max_deg) * 22 if max_deg else 12,
            "title": f"{lab}\nConnection weight: {degree[lab]:.2f}",
        }
        for lab in labels
    ]

    max_w = max((e["weight"] for e in edge_specs), default=1.0)
    edges = [
        {
            "from": e["from"],
            "to": e["to"],
            "value": 1 + (e["weight"] / max_w) * 8,
            "weight": e["weight"],
            "polarity": e["polarity"],
            "title": f"{e['from']} — {e['to']}: {e['weight']:.3f}",
        }
        for e in edge_specs
    ]

    return prune_graph_to_linked(
        {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "kind": kind,
            },
        }
    )


def graphs_from_matrices(matrices: dict[str, dict]) -> dict[str, dict]:
    return {
        key: matrix_to_graph(payload["labels"], payload["values"], key)
        for key, payload in matrices.items()
    }
