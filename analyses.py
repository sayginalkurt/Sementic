"""Üç ağ analizi için kelime × kelime matrisleri."""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from preprocess import build_vocabulary, tokens_by_sentence


def _empty_matrix(vocab: list[str]) -> pd.DataFrame:
    return pd.DataFrame(0.0, index=vocab, columns=vocab)


def cooccurrence_matrix(
    sentences: list[list[str]],
    vocab: list[str],
    *,
    binary: bool = False,
) -> pd.DataFrame:
    """
    Co-occurrence Network Analysis.
    Aynı cümlede (stanza) birlikte geçen kelime çiftlerini sayar.
    """
    idx = {w: i for i, w in enumerate(vocab)}
    n = len(vocab)
    mat = np.zeros((n, n), dtype=float)

    for tokens in sentences:
        present = sorted({t for t in tokens if t in idx})
        for a, b in combinations(present, 2):
            i, j = idx[a], idx[b]
            mat[i, j] += 1
            mat[j, i] += 1
        if not binary:
            for w in present:
                i = idx[w]
                mat[i, i] += 1

    return pd.DataFrame(mat, index=vocab, columns=vocab)


def semantic_matrix(
    sentences: list[list[str]],
    vocab: list[str],
) -> pd.DataFrame:
    """
    Semantic Network Analysis (dağılımsal anlambilim).
    Kelimeleri cümle bağlamında TF-IDF ile vektörler; kosinüs benzerliği = anlamsal yakınlık.
    """
    if len(vocab) < 2:
        return _empty_matrix(vocab)

    vocab_set = set(vocab)
    docs = [" ".join(t for t in sent if t in vocab_set) for sent in sentences]
    docs = [d for d in docs if d.strip()]
    if not docs:
        return _empty_matrix(vocab)

    vectorizer = TfidfVectorizer(
        vocabulary=vocab,
        tokenizer=str.split,
        preprocessor=None,
        token_pattern=None,
        lowercase=False,
        norm="l2",
    )
    doc_term = vectorizer.fit_transform(docs)
    # Terim-terim: her kelimenin dokümanlardaki bağlam vektörü
    term_context = doc_term.T  # vocab × docs
    sim = cosine_similarity(term_context)
    np.fill_diagonal(sim, 1.0)
    return pd.DataFrame(sim, index=vocab, columns=vocab)


def epistemic_matrix(
    sentences: list[list[str]],
    vocab: list[str],
    *,
    include_lag: bool = True,
    lag_weight: float = 0.5,
) -> pd.DataFrame:
    """
    Epistemic Network Analysis (ENA) — kelime düzeyinde yaklaşım.
    - Eşzamanlı (concurrent): aynı cümlede birlikte aktif kodlar
    - Gecikmeli (lagged): ardışık cümleler arası bağlantılar (isteğe bağlı)
    - ENA merkezileştirmesi: gözlenen eş-oluşumdan beklenen (marjinal) çıkarılır
    """
    idx = {w: i for i, w in enumerate(vocab)}
    n = len(vocab)
    raw = np.zeros((n, n), dtype=float)

    def add_pairs(words: list[str], weight: float = 1.0) -> None:
        present = sorted({w for w in words if w in idx})
        for a, b in combinations(present, 2):
            i, j = idx[a], idx[b]
            raw[i, j] += weight
            raw[j, i] += weight

    for tokens in sentences:
        add_pairs(tokens, 1.0)

    if include_lag and len(sentences) > 1:
        for prev, curr in zip(sentences[:-1], sentences[1:]):
            prev_set = [w for w in prev if w in idx]
            curr_set = [w for w in curr if w in idx]
            for a in prev_set:
                for b in curr_set:
                    if a == b:
                        continue
                    i, j = idx[a], idx[b]
                    raw[i, j] += lag_weight
                    raw[j, i] += lag_weight

    # ENA-style centering: S - (row_sum * col_sum) / total
    total = raw.sum()
    if total > 0:
        row_sum = raw.sum(axis=1, keepdims=True)
        col_sum = raw.sum(axis=0, keepdims=True)
        expected = (row_sum @ col_sum) / total
        centered = raw - expected
    else:
        centered = raw

    return pd.DataFrame(centered, index=vocab, columns=vocab)


def dataframe_to_payload(df: pd.DataFrame) -> dict:
    labels = [str(x) for x in df.index.tolist()]
    return {
        "labels": labels,
        "values": df.values.tolist(),
    }


def run_all_analyses_from_sentences(
    sentences: list[list[str]],
    *,
    min_freq: int = 2,
) -> tuple[list[str], dict[str, pd.DataFrame]]:
    vocab = build_vocabulary(sentences, min_freq=min_freq)
    if not vocab:
        raise ValueError(
            "Sözlük boş. Metni genişletin veya min_freq değerini düşürün."
        )

    matrices = {
        "cooccurrence": cooccurrence_matrix(sentences, vocab),
        "semantic": semantic_matrix(sentences, vocab),
        "epistemic": epistemic_matrix(sentences, vocab),
    }
    return vocab, matrices


def run_all_analyses(
    text: str,
    *,
    min_freq: int = 2,
    min_word_len: int = 2,
) -> tuple[list[str], dict[str, pd.DataFrame]]:
    sentences = tokens_by_sentence(text, min_len=min_word_len)
    return run_all_analyses_from_sentences(sentences, min_freq=min_freq)
