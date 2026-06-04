"""Shared Sementic analysis pipeline (web + Places reviews)."""

from __future__ import annotations

from ai_preprocess import concepts_preview, extract_concepts_with_ai
from ai_relations import annotate_graphs_with_relations, matrices_from_directed_graphs
from analyses import dataframe_to_payload, run_all_analyses_from_sentences
from graph import graphs_from_matrices

MIN_ANALYSIS_TEXT_LEN = 20

MATRIX_LABELS = {
    "cooccurrence": "Co-occurrence",
    "semantic": "Semantic",
    "epistemic": "Epistemic (ENA)",
}


def run_sementic_analysis(raw_text: str, *, min_freq: int = 0) -> dict:
    """
    Full pipeline: translate → concepts → matrices → graphs → directed relations.
    Raises RuntimeError, ValueError, or other exceptions from downstream modules.
    """
    raw = raw_text.strip()
    if len(raw) < MIN_ANALYSIS_TEXT_LEN:
        raise ValueError(
            f"Text must be at least {MIN_ANALYSIS_TEXT_LEN} characters for analysis."
        )

    sentences, _concept_list, english_sentences = extract_concepts_with_ai(raw)
    vocab, matrices = run_all_analyses_from_sentences(sentences, min_freq=min_freq)

    matrix_payload = {
        key: dataframe_to_payload(df) for key, df in matrices.items()
    }
    graphs = graphs_from_matrices(matrix_payload)
    english_text = "\n".join(english_sentences)
    graphs = annotate_graphs_with_relations(graphs, english_text)
    matrix_payload = matrices_from_directed_graphs(
        graphs, {k: v["labels"] for k, v in matrix_payload.items()}
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
