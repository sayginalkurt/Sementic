"""Pipeline step definitions and progress events for the lab UI."""

from __future__ import annotations

from typing import Any, Callable

ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]

ANALYSIS_STEPS: list[dict[str, str]] = [
    {"id": "normalize", "num": "01", "label": "NORMALIZE & SPLIT"},
    {"id": "translate", "num": "02", "label": "TRANSLATE → EN"},
    {"id": "concepts", "num": "03", "label": "CONCEPT EXTRACTION"},
    {"id": "vocabulary", "num": "04", "label": "VOCABULARY FILTER"},
    {"id": "matrices", "num": "05", "label": "STAT MATRICES ×3"},
    {"id": "graphs", "num": "06", "label": "BASE GRAPH BUILD"},
    {"id": "relations_co", "num": "07", "label": "AI RELATIONS · CO"},
    {"id": "relations_se", "num": "08", "label": "AI RELATIONS · SE"},
    {"id": "relations_ep", "num": "09", "label": "AI RELATIONS · EP"},
    {"id": "sign_matrices", "num": "10", "label": "SIGNED MATRIX OUT"},
    {"id": "complete", "num": "11", "label": "PIPELINE COMPLETE"},
]

FCM_STEPS: list[dict[str, str]] = [
    {"id": "normalize", "num": "01", "label": "NORMALIZE & SPLIT"},
    {"id": "lang_detect", "num": "02", "label": "LANG DETECT"},
    {"id": "translate", "num": "03", "label": "TRANSLATE (skip if EN)"},
    {"id": "phrase_extract", "num": "04", "label": "PHRASE EXTRACT (NLP)"},
    {"id": "phrase_cluster", "num": "05", "label": "PHRASE CLUSTER (embed)"},
    {"id": "concept_merge", "num": "06", "label": "CONCEPT MERGE (LLM)"},
    {"id": "polarity_context", "num": "07", "label": "POLARITY CONTEXT"},
    {"id": "fcm_edges", "num": "08", "label": "FCM EDGE INFERENCE"},
    {"id": "adjacency_matrix", "num": "09", "label": "ADJACENCY MATRIX"},
    {"id": "graph_render", "num": "10", "label": "GRAPH RENDER"},
    {"id": "complete", "num": "11", "label": "PIPELINE COMPLETE"},
]

PLACES_EXTRA_STEPS: list[dict[str, str]] = [
    {"id": "place_fetch", "num": "P1", "label": "FETCH REVIEWS"},
    {"id": "batch_dispatch", "num": "P2", "label": "BATCH DISPATCH"},
    {"id": "batch_complete", "num": "P3", "label": "BATCH COMPLETE"},
]

RELATION_STEP_BY_KIND = {
    "cooccurrence": "relations_co",
    "semantic": "relations_se",
    "epistemic": "relations_ep",
}

VALID_PIPELINES = frozenset({"statistical", "fcm"})


def normalize_pipeline(pipeline: str | None) -> str:
    p = (pipeline or "statistical").strip().lower()
    return p if p in VALID_PIPELINES else "statistical"


def emit(
    callback: ProgressCallback | None,
    step: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    if callback:
        callback(step, status, detail or {})


def progress_event(step: str, status: str, detail: dict[str, Any] | None = None) -> dict:
    return {
        "type": "progress",
        "step": step,
        "status": status,
        "detail": detail or {},
    }
