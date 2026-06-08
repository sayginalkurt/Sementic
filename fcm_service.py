"""FCM analysis pipeline orchestrator."""

from __future__ import annotations

import os

from ai_preprocess import _openai_client, normalize_text, sentences_from_text
from concept_hybrid import extract_fcm_document_concepts
from fcm_inference import infer_fcm_edges, infer_polarity_context
from fcm_matrix import adjacency_from_edges, fcm_graph_from_edges
from graph import linked_label_set
from lang_detect import detect_language, prepare_english_sentences
from workflow import ProgressCallback, emit

MIN_ANALYSIS_TEXT_LEN = 20


def run_fcm_analysis(
    raw_text: str,
    *,
    on_progress: ProgressCallback | None = None,
    review_index: int | None = None,
) -> dict:
    raw = raw_text.strip()
    if len(raw) < MIN_ANALYSIS_TEXT_LEN:
        raise ValueError(
            f"Text must be at least {MIN_ANALYSIS_TEXT_LEN} characters for analysis."
        )

    ctx: dict = {}
    if review_index is not None:
        ctx["review_index"] = review_index

    emit(on_progress, "normalize", "running", ctx)
    text = normalize_text(raw)
    source_sentences = sentences_from_text(text)
    if not source_sentences:
        emit(on_progress, "normalize", "error", {**ctx, "reason": "no sentences"})
        raise ValueError("No sentences found in the text.")
    emit(on_progress, "normalize", "done", {**ctx, "sentences": len(source_sentences)})

    emit(on_progress, "lang_detect", "running", ctx)
    lang_info = detect_language(raw)
    emit(
        on_progress,
        "lang_detect",
        "done",
        {**ctx, "code": lang_info.get("code"), "is_english": lang_info.get("is_english")},
    )

    client = _openai_client()
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    english_sentences, language = prepare_english_sentences(
        source_sentences,
        client=client,
        model=model,
        on_progress=on_progress,
        progress_ctx=ctx,
        language_info=lang_info,
    )
    english_text = "\n".join(english_sentences)

    emit(on_progress, "phrase_extract", "running", ctx)
    extracted = extract_fcm_document_concepts(
        english_sentences,
        client=client,
        model=model,
    )
    concepts = extracted.get("concepts") or []
    phrase_map = extracted.get("phrase_map") or []
    concepts_by_sentence = extracted.get("concepts_by_sentence") or []
    if not concepts:
        raise ValueError("No concepts extracted from text.")
    emit(
        on_progress,
        "phrase_extract",
        "done",
        {**ctx, "concepts": len(concepts), "mode": "document_thematic"},
    )

    emit(
        on_progress,
        "phrase_cluster",
        "done",
        {**ctx, "skipped": True, "reason": "document-level categories"},
    )

    emit(on_progress, "concept_merge", "running", ctx)
    emit(
        on_progress,
        "concept_merge",
        "done",
        {**ctx, "concepts": len(concepts)},
    )

    emit(on_progress, "polarity_context", "running", ctx)
    polarity_context = infer_polarity_context(
        english_text, concepts, client=client, model=model
    )
    emit(
        on_progress,
        "polarity_context",
        "done",
        {**ctx, "review_tone": polarity_context.get("review_tone")},
    )

    emit(on_progress, "fcm_edges", "running", ctx)
    edges = infer_fcm_edges(
        english_text,
        concepts,
        phrase_map,
        polarity_context,
        client=client,
        model=model,
    )
    emit(on_progress, "fcm_edges", "done", {**ctx, "edges": len(edges)})

    linked = linked_label_set(edges, src_key="source", tgt_key="target")
    concepts = [c for c in concepts if c["label"] in linked]
    edges = [
        e
        for e in edges
        if e.get("source") in linked and e.get("target") in linked
    ]
    phrase_map = [p for p in phrase_map if p.get("concept_label") in linked]
    valence = polarity_context.get("concept_valence") or []
    polarity_context["concept_valence"] = [
        v for v in valence if v.get("label") in linked or v.get("concept") in linked
    ]

    emit(on_progress, "adjacency_matrix", "running", ctx)
    matrix = adjacency_from_edges(concepts, edges)
    emit(on_progress, "adjacency_matrix", "done", ctx)

    emit(on_progress, "graph_render", "running", ctx)
    graph = fcm_graph_from_edges(concepts, edges)
    emit(on_progress, "graph_render", "done", {**ctx, "edges": len(edges)})

    vocab_size = len(concepts)
    emit(
        on_progress,
        "complete",
        "done",
        {**ctx, "sentence_count": len(english_sentences), "vocabulary_size": vocab_size},
    )

    return {
        "pipeline": "fcm",
        "language": language,
        "review_tone": polarity_context.get("review_tone", "mixed"),
        "concept_valence": polarity_context.get("concept_valence", []),
        "english_sentences": english_sentences,
        "concepts_by_sentence": concepts_by_sentence,
        "phrases": extracted.get("phrases") or [],
        "phrase_clusters": extracted.get("phrase_clusters") or [],
        "concepts": concepts,
        "phrase_map": phrase_map,
        "edges": edges,
        "matrix": matrix,
        "graph": graph,
        "sentence_count": len(english_sentences),
        "vocabulary_size": vocab_size,
    }
