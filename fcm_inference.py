"""FCM: contextual polarity + causal directed edges."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from ai_preprocess import _chat_json, _openai_client

POLARITY_SYSTEM = """You assess qualitative review tone and per-concept valence in context.

Consider ambivalence: e.g. "not very large" may be neutral-to-positive when followed by "well organized and easy to explore without feeling overwhelmed" — small size increases navigability.

Return JSON only:
{
  "review_tone": "mostly_positive|mixed|mostly_negative",
  "concept_valence": [
    {"concept": "...", "valence": "positive|negative|neutral|ambivalent", "note": "..."}
  ]
}"""

POLARITY_USER = """English text:
---
{text}
---

Concepts:
{concepts_json}"""

FCM_EDGE_SYSTEM = """You build a Fuzzy Cognitive Map (FCM) from qualitative text.

Infer CAUSAL or INFLUENCE relations between concepts (not mere co-occurrence). Example:
organization / manageable size → lower overwhelm → better visitor experience

For each directed edge provide:
- source: source concept label (exact match from list)
- target: target concept label (exact match from list)
- weight: integer -2, -1, 0, +1, or +2
  +1 = positive influence, -1 = negative influence
  +2 = strong positive, -2 = strong negative
  0 = no direct relation (omit edges with weight 0)
- strength: weak | medium | strong (weak/medium → ±1, strong → ±2)
- polarity: positive | negative (sign of influence)
- evidence_sentence: exact or near-exact quote from the text supporting this edge
- analyst_note: brief interpretation (note ambivalence when relevant)

Rules:
- Only use concept labels from the provided list
- Include all well-evidenced causal links (richer maps are better when supported by text)
- Do not invent relations without evidence in the text
- Respect review tone and concept valence context
- Return JSON only: {"edges": [...]}"""

FCM_EDGE_USER = """Review tone: {review_tone}

Concept valence context:
{valence_json}

English text:
---
{text}
---

Concepts (use these labels exactly):
{concepts_json}

Phrase evidence map:
{phrase_map_json}"""

_VALID_WEIGHTS = frozenset({-2, -1, 0, 1, 2})
_VALID_STRENGTH = frozenset({"weak", "medium", "strong"})
_VALID_POLARITY = frozenset({"positive", "negative"})


def _strength_to_weight(strength: str, polarity: str, weight: int) -> int:
    if weight in _VALID_WEIGHTS and weight != 0:
        return weight
    sign = -1 if polarity == "negative" else 1
    if strength == "strong":
        return sign * 2
    return sign * 1


def infer_polarity_context(
    english_text: str,
    concepts: list[dict[str, Any]],
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    oai = client or _openai_client()
    chosen = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    labels = [c["label"] for c in concepts]

    data = _chat_json(
        oai,
        chosen,
        system=POLARITY_SYSTEM,
        user=POLARITY_USER.format(
            text=english_text[:80000],
            concepts_json=json.dumps(labels, ensure_ascii=False),
        ),
    )

    tone = str(data.get("review_tone", "mixed")).strip().lower()
    if tone not in ("mostly_positive", "mixed", "mostly_negative"):
        tone = "mixed"

    valence = data.get("concept_valence") or []
    if not isinstance(valence, list):
        valence = []

    return {"review_tone": tone, "concept_valence": valence}


def infer_fcm_edges(
    english_text: str,
    concepts: list[dict[str, Any]],
    phrase_map: list[dict[str, Any]],
    polarity_context: dict[str, Any],
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    oai = client or _openai_client()
    chosen = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    labels = {c["label"] for c in concepts}
    label_list = [c["label"] for c in concepts]

    data = _chat_json(
        oai,
        chosen,
        system=FCM_EDGE_SYSTEM,
        user=FCM_EDGE_USER.format(
            review_tone=polarity_context.get("review_tone", "mixed"),
            valence_json=json.dumps(
                polarity_context.get("concept_valence") or [],
                ensure_ascii=False,
            ),
            text=english_text[:80000],
            concepts_json=json.dumps(label_list, ensure_ascii=False),
            phrase_map_json=json.dumps(phrase_map[:80], ensure_ascii=False),
        ),
    )

    raw_edges = data.get("edges") or []
    edges: list[dict[str, Any]] = []

    for item in raw_edges:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip().lower()
        target = str(item.get("target", "")).strip().lower()
        if not source or not target or source == target:
            continue
        if source not in labels or target not in labels:
            continue

        polarity = str(item.get("polarity", "positive")).strip().lower()
        strength = str(item.get("strength", "medium")).strip().lower()
        if polarity not in _VALID_POLARITY:
            polarity = "positive"
        if strength not in _VALID_STRENGTH:
            strength = "medium"

        try:
            weight = int(item.get("weight", 0))
        except (TypeError, ValueError):
            weight = 0
        weight = _strength_to_weight(strength, polarity, weight)
        if weight == 0:
            continue

        edges.append(
            {
                "source": source,
                "target": target,
                "weight": weight,
                "strength": strength,
                "polarity": polarity,
                "evidence_sentence": str(item.get("evidence_sentence", "")).strip(),
                "analyst_note": str(item.get("analyst_note", "")).strip(),
            }
        )

    return edges
