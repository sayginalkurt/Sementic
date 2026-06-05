"""Hybrid concept extraction: NLP phrases → embedding clusters → LLM merge."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI
from sklearn.cluster import AgglomerativeClustering

from ai_preprocess import _chat_json, _openai_client

CONCEPT_MERGE_SYSTEM = """You are a qualitative research analyst labeling extracted phrases for a fuzzy cognitive map.

Prefer FINE-GRAINED concepts that keep the network rich. Merge ONLY when phrases are near-paraphrases or unmistakably the same idea.

Examples of justified merge:
- "open spaces", "great views of the water" → "views and open space" (same theme)
Do NOT collapse unrelated phrases into one broad bucket like "overall quality".

Rules:
- English concept labels (2–5 words), specific rather than generic
- Every phrase maps to exactly one concept
- Keep most distinct phrases as separate concepts when in doubt
- Return valid JSON only"""

CONCEPT_MERGE_USER = """English text (by sentence):
{sentences_json}

Phrase clusters from NLP + embedding (cluster_id → phrases):
{clusters_json}

Target roughly {target_concepts} concepts (between {min_concepts} and {max_concepts}). Do not over-merge.

Return JSON:
{{
  "concepts": [
    {{"id": "c1", "label": "concept label", "phrases": ["phrase1", "phrase2"]}}
  ],
  "phrase_map": [
    {{"sentence_idx": 0, "phrase": "...", "concept_id": "c1"}}
  ]
}}"""

_SPACY_NLP = None
_MIN_PHRASE_LEN = 3
_EMBED_MODEL = "text-embedding-3-small"
# Skip embedding merge when few phrases; keep one cluster per phrase
_CLUSTER_SKIP_BELOW = 12
# When clustering, keep ~85% of unique phrases as separate groups
_CLUSTER_RATIO = 0.85


def _get_spacy():
    global _SPACY_NLP
    if _SPACY_NLP is not None:
        return _SPACY_NLP
    try:
        import spacy

        _SPACY_NLP = spacy.load("en_core_web_sm")
    except OSError as exc:
        raise RuntimeError(
            "spaCy English model missing. Run: python -m spacy download en_core_web_sm"
        ) from exc
    return _SPACY_NLP


def _normalize_phrase(text: str) -> str:
    t = re.sub(r"\s+", " ", text.strip().lower())
    return t


def extract_phrases(sentences: list[str]) -> list[dict[str, Any]]:
    """Extract noun phrases per sentence via spaCy."""
    nlp = _get_spacy()
    phrases: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    for idx, sent in enumerate(sentences):
        if not sent.strip():
            continue
        doc = nlp(sent)
        candidates: list[str] = []

        for chunk in doc.noun_chunks:
            p = _normalize_phrase(chunk.text)
            if len(p) >= _MIN_PHRASE_LEN:
                candidates.append(p)

        for token in doc:
            if token.pos_ in ("NOUN", "PROPN") and len(token.text) >= 4:
                p = _normalize_phrase(token.text)
                if len(p) >= _MIN_PHRASE_LEN:
                    candidates.append(p)

        for p in candidates:
            key = (idx, p)
            if key in seen:
                continue
            seen.add(key)
            phrases.append({"sentence_idx": idx, "phrase": p})

    if not phrases and sentences:
        for idx, sent in enumerate(sentences):
            words = [w for w in re.findall(r"[a-z]{4,}", sent.lower())]
            for w in words[:5]:
                phrases.append({"sentence_idx": idx, "phrase": w})

    return phrases


def _embed_phrases(client: OpenAI, unique_phrases: list[str]) -> list[list[float]]:
    if not unique_phrases:
        return []
    resp = client.embeddings.create(model=_EMBED_MODEL, input=unique_phrases)
    return [item.embedding for item in resp.data]


def cluster_phrases(
    phrases: list[dict[str, Any]],
    *,
    client: OpenAI | None = None,
) -> list[dict[str, Any]]:
    """Cluster unique phrases by embedding similarity (light merge)."""
    if not phrases:
        return []

    unique = sorted({p["phrase"] for p in phrases})
    if len(unique) == 1:
        return [{"cluster_id": 0, "phrases": unique}]

    # Short texts: no embedding merge — one cluster per phrase
    if len(unique) < _CLUSTER_SKIP_BELOW:
        return [
            {"cluster_id": i, "phrases": [phrase]}
            for i, phrase in enumerate(unique)
        ]

    oai = client or _openai_client()
    vectors = _embed_phrases(oai, unique)

    # High cluster count → only merge very similar phrases
    n_clusters = max(2, int(round(len(unique) * _CLUSTER_RATIO)))
    n_clusters = min(n_clusters, len(unique))

    clustering = AgglomerativeClustering(
        n_clusters=n_clusters,
        metric="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(vectors)

    buckets: dict[int, list[str]] = {}
    for phrase, label in zip(unique, labels):
        buckets.setdefault(int(label), []).append(phrase)

    return [
        {"cluster_id": cid, "phrases": sorted(ps)}
        for cid, ps in sorted(buckets.items())
    ]


def merge_concepts_with_llm(
    sentences: list[str],
    phrase_clusters: list[dict[str, Any]],
    phrases: list[dict[str, Any]],
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """LLM merges phrase clusters into higher-level concepts."""
    oai = client or _openai_client()
    chosen = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    if not phrase_clusters:
        return {"concepts": [], "phrase_map": []}

    n_clusters = len(phrase_clusters)
    min_concepts = max(2, int(round(n_clusters * 0.55)))
    target_concepts = max(min_concepts, int(round(n_clusters * 0.75)))
    max_concepts = n_clusters

    if n_clusters <= 3:
        concepts = [
            {
                "id": f"c{i + 1}",
                "label": c["phrases"][0] if c["phrases"] else f"concept_{i + 1}",
                "phrases": c["phrases"],
            }
            for i, c in enumerate(phrase_clusters)
        ]
        phrase_map = []
        for i, c in enumerate(phrase_clusters):
            for p in phrases:
                if p["phrase"] in c["phrases"]:
                    phrase_map.append(
                        {
                            "sentence_idx": p["sentence_idx"],
                            "phrase": p["phrase"],
                            "concept_id": f"c{i + 1}",
                            "concept_label": concepts[i]["label"],
                        }
                    )
        return {"concepts": concepts, "phrase_map": phrase_map}

    data = _chat_json(
        oai,
        chosen,
        system=CONCEPT_MERGE_SYSTEM,
        user=CONCEPT_MERGE_USER.format(
            sentences_json=json.dumps(sentences, ensure_ascii=False),
            clusters_json=json.dumps(phrase_clusters, ensure_ascii=False),
            target_concepts=target_concepts,
            min_concepts=min_concepts,
            max_concepts=max_concepts,
        ),
    )

    raw_concepts = data.get("concepts") or []
    concepts: list[dict[str, Any]] = []
    label_set: set[str] = set()

    for i, item in enumerate(raw_concepts):
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or f"c{i + 1}")
        label = str(item.get("label") or "").strip().lower()
        if not label:
            continue
        phr = item.get("phrases") or []
        if not isinstance(phr, list):
            phr = []
        concepts.append(
            {
                "id": cid,
                "label": label,
                "phrases": [_normalize_phrase(str(p)) for p in phr if str(p).strip()],
            }
        )
        label_set.add(label)

    phrase_map_raw = data.get("phrase_map") or []
    phrase_map: list[dict[str, Any]] = []
    for item in phrase_map_raw:
        if not isinstance(item, dict):
            continue
        phrase = _normalize_phrase(str(item.get("phrase", "")))
        cid = str(item.get("concept_id", ""))
        if not phrase or not cid:
            continue
        phrase_map.append(
            {
                "sentence_idx": int(item.get("sentence_idx", 0)),
                "phrase": phrase,
                "concept_id": cid,
            }
        )

    if not concepts or len(concepts) < min_concepts:
        concepts = [
            {
                "id": f"c{i + 1}",
                "label": c["phrases"][0] if c["phrases"] else f"concept_{i + 1}",
                "phrases": c["phrases"],
            }
            for i, c in enumerate(phrase_clusters)
        ]
        phrase_map = []
        for i, c in enumerate(phrase_clusters):
            for p in phrases:
                if p["phrase"] in c["phrases"]:
                    phrase_map.append(
                        {
                            "sentence_idx": p["sentence_idx"],
                            "phrase": p["phrase"],
                            "concept_id": f"c{i + 1}",
                            "concept_label": concepts[i]["label"],
                        }
                    )
        return {"concepts": concepts, "phrase_map": phrase_map}

    id_to_label = {c["id"]: c["label"] for c in concepts}
    for p in phrases:
        if any(m["phrase"] == p["phrase"] for m in phrase_map):
            continue
        match = next(
            (c for c in concepts if p["phrase"] in c.get("phrases", [])),
            concepts[0] if concepts else None,
        )
        if match:
            phrase_map.append(
                {
                    "sentence_idx": p["sentence_idx"],
                    "phrase": p["phrase"],
                    "concept_id": match["id"],
                }
            )

    for m in phrase_map:
        m["concept_label"] = id_to_label.get(m["concept_id"], "")

    return {"concepts": concepts, "phrase_map": phrase_map}
