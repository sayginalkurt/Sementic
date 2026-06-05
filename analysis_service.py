"""Shared Sementic analysis pipeline (web + Places reviews)."""

from __future__ import annotations

import os

from ai_preprocess import (
    _extract_concepts_from_english,
    _openai_client,
    concepts_preview,
    normalize_text,
    sentences_from_text,
    translate_sentences_to_english,
)
from ai_relations import annotate_graphs_with_relations, matrices_from_directed_graphs
from analyses import dataframe_to_payload, run_all_analyses_from_sentences
from graph import graphs_from_matrices
from workflow import ProgressCallback, emit

MIN_ANALYSIS_TEXT_LEN = 20

MATRIX_LABELS = {
    "cooccurrence": "Co-occurrence",
    "semantic": "Semantic",
    "epistemic": "Epistemic (ENA)",
}


def run_sementic_analysis(
    raw_text: str,
    *,
    min_freq: int = 0,
    on_progress: ProgressCallback | None = None,
    review_index: int | None = None,
) -> dict:
    """
    Full pipeline: translate → concepts → matrices → graphs → directed relations.
    Raises RuntimeError, ValueError, or other exceptions from downstream modules.
    """
    raw = raw_text.strip()
    if len(raw) < MIN_ANALYSIS_TEXT_LEN:
        raise ValueError(
            f"Text must be at least {MIN_ANALYSIS_TEXT_LEN} characters for analysis."
        )

    ctx = {"review_index": review_index} if review_index is not None else {}

    emit(on_progress, "normalize", "running", ctx)
    text = normalize_text(raw)
    source_sentences = sentences_from_text(text)
    if not source_sentences:
        emit(on_progress, "normalize", "error", {**ctx, "reason": "no sentences"})
        raise ValueError("No sentences found in the text.")
    emit(
        on_progress,
        "normalize",
        "done",
        {**ctx, "sentences": len(source_sentences)},
    )

    client = _openai_client()
    chosen_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    emit(on_progress, "translate", "running", {**ctx, "sentences": len(source_sentences)})
    english_sentences = translate_sentences_to_english(
        source_sentences,
        client=client,
        model=chosen_model,
        on_progress=on_progress,
        progress_ctx=ctx,
    )
    emit(
        on_progress,
        "translate",
        "done",
        {**ctx, "sentences": len(english_sentences)},
    )

    emit(on_progress, "concepts", "running", ctx)
    sentences = _extract_concepts_from_english(
        english_sentences, client=client, model=chosen_model
    )
    non_empty = [c for c in sentences if c]
    if not non_empty:
        emit(on_progress, "concepts", "error", {**ctx, "reason": "no concepts"})
        raise ValueError("No valid concepts extracted. Check the input text.")
    emit(
        on_progress,
        "concepts",
        "done",
        {**ctx, "concepts": len({w for s in sentences for w in s})},
    )

    emit(on_progress, "vocabulary", "running", {**ctx, "min_freq": min_freq})
    vocab, matrices = run_all_analyses_from_sentences(sentences, min_freq=min_freq)
    emit(
        on_progress,
        "vocabulary",
        "done",
        {**ctx, "vocabulary_size": len(vocab)},
    )

    emit(on_progress, "matrices", "running", ctx)
    matrix_payload = {
        key: dataframe_to_payload(df) for key, df in matrices.items()
    }
    emit(on_progress, "matrices", "done", {**ctx, "types": list(matrix_payload)})

    emit(on_progress, "graphs", "running", ctx)
    graphs = graphs_from_matrices(matrix_payload)
    edge_total = sum(len(g.get("edges") or []) for g in graphs.values())
    emit(on_progress, "graphs", "done", {**ctx, "edges": edge_total})

    english_text = "\n".join(english_sentences)
    graphs = annotate_graphs_with_relations(
        graphs,
        english_text,
        client=client,
        model=chosen_model,
        on_progress=on_progress,
        progress_ctx=ctx,
    )

    emit(on_progress, "sign_matrices", "running", ctx)
    matrix_payload = matrices_from_directed_graphs(
        graphs, {k: v["labels"] for k, v in matrix_payload.items()}
    )
    emit(on_progress, "sign_matrices", "done", ctx)

    emit(
        on_progress,
        "complete",
        "done",
        {
            **ctx,
            "sentence_count": len(sentences),
            "vocabulary_size": len(vocab),
        },
    )

    return {
        "sentence_count": len(sentences),
        "vocabulary_size": len(vocab),
        "vocabulary": vocab,
        "english_sentences": english_sentences,
        "concepts_by_sentence": sentences,
        "concept_frequency": concepts_preview(sentences),
        "matrices": matrix_payload,
        "graphs": graphs,
        "matrix_labels": MATRIX_LABELS,
    }
