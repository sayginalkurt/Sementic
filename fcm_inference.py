"""FCM: contextual polarity + causal directed edges."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from ai_preprocess import _chat_json, _openai_client
from sign_scale import SCALE_PROMPT, resolve_edge_weight, strength_from_weight, weight_label

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
- weight: one of -1, -0.5, -0.25, 0.25, 0.5, 1 (omit weight 0)
- strength: weak | medium | strong — must match |weight|: weak=0.25, medium=0.5, strong=1
- polarity: positive | negative (sign of influence)
- evidence_sentence: exact or near-exact quote from the text supporting this edge
- analyst_note: brief interpretation (note ambivalence when relevant)

{scale_prompt}

Rules:
- Only use concept labels listed under Concepts below (derived from this same text in an earlier step — do not invent new labels)
- Include all well-evidenced causal links (richer maps are better when supported by text)
- Do not invent relations without evidence in the text
- Respect review tone and concept valence context
- Return JSON only: {{"edges": [...]}}"""

FCM_EDGE_USER = """Review tone: {review_tone}

Concept valence context:
{valence_json}

English text:
---
{text}
---

Concepts (use these labels exactly — extracted from this text, not a fixed external vocabulary):
{concepts_json}

Phrase evidence map:
{phrase_map_json}"""

_VALID_STRENGTH = frozenset({"weak", "medium", "strong"})
_VALID_POLARITY = frozenset({"positive", "negative"})


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
    label_list = [c["label"] for c in concepts]
    label_by_lower = {lab.lower(): lab for lab in label_list}

    data = _chat_json(
        oai,
        chosen,
        system=FCM_EDGE_SYSTEM.format(scale_prompt=SCALE_PROMPT),
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
        source = label_by_lower.get(str(item.get("source", "")).strip().lower())
        target = label_by_lower.get(str(item.get("target", "")).strip().lower())
        if not source or not target or source == target:
            continue

        polarity = str(item.get("polarity", "positive")).strip().lower()
        strength = str(item.get("strength", "medium")).strip().lower()
        if polarity not in _VALID_POLARITY:
            polarity = "positive"
        if strength not in _VALID_STRENGTH:
            strength = "medium"

        try:
            raw_weight = item.get("weight", 0)
        except (TypeError, ValueError):
            raw_weight = 0
        weight = resolve_edge_weight(
            raw_weight, strength=strength, polarity=polarity
        )
        if weight == 0:
            continue
        strength = strength_from_weight(weight)

        edges.append(
            {
                "source": source,
                "target": target,
                "weight": weight,
                "weight_label": weight_label(weight),
                "strength": strength,
                "polarity": polarity,
                "evidence_sentence": str(item.get("evidence_sentence", "")).strip(),
                "analyst_note": str(item.get("analyst_note", "")).strip(),
            }
        )

    return edges
