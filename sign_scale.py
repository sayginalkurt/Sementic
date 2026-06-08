"""Signed edge weight scale shared by STAT and FCM pipelines."""

from __future__ import annotations

from typing import Any

SCALE_VALUES: tuple[float, ...] = (-1.0, -0.5, -0.25, 0.25, 0.5, 1.0)

SCALE_LABELS: dict[float, str] = {
    -1.0: "strong negative",
    -0.5: "negative",
    -0.25: "weak negative",
    0.25: "weak positive",
    0.5: "positive",
    1.0: "strong positive",
}

VALID_STRENGTH = frozenset({"weak", "medium", "strong"})
VALID_POLARITY = frozenset({"positive", "negative"})

STRENGTH_TO_MAGNITUDE: dict[str, float] = {
    "weak": 0.25,
    "medium": 0.5,
    "strong": 1.0,
}

_LEGACY_INT_WEIGHTS: dict[int, float] = {
    -2: -1.0,
    -1: -0.5,
    1: 0.5,
    2: 1.0,
}

SCALE_PROMPT = """Signed weight scale (use exactly one value per edge):
  -1    strong negative
  -0.5  negative
  -0.25 weak negative
   0.25 weak positive
   0.5  positive
   1    strong positive

Alternatively set strength (weak | medium | strong) + polarity (positive | negative):
  weak + negative → -0.25, medium + negative → -0.5, strong + negative → -1
  weak + positive → +0.25, medium + positive → +0.5, strong + positive → +1"""


def strength_polarity_to_weight(strength: str, polarity: str) -> float:
    s = strength if strength in VALID_STRENGTH else "medium"
    p = polarity if polarity in VALID_POLARITY else "positive"
    mag = STRENGTH_TO_MAGNITUDE[s]
    return -mag if p == "negative" else mag


def normalize_weight(raw: Any) -> float:
    """Snap a raw weight to the nearest allowed scale value."""
    if raw is None:
        return 0.0
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if abs(v) < 1e-12:
        return 0.0

    for s in SCALE_VALUES:
        if abs(v - s) < 1e-9:
            return s

    if float(int(round(v))) == v:
        legacy = _LEGACY_INT_WEIGHTS.get(int(v))
        if legacy is not None:
            return legacy

    sign = -1.0 if v < 0 else 1.0
    mag = min(abs(v), 1.0)
    nearest_mag = min(STRENGTH_TO_MAGNITUDE.values(), key=lambda m: abs(m - mag))
    return sign * nearest_mag


def resolve_edge_weight(
    raw_weight: Any,
    *,
    strength: str = "medium",
    polarity: str = "positive",
) -> float:
    """Prefer explicit weight; fall back to strength × polarity."""
    w = normalize_weight(raw_weight)
    if w != 0.0:
        return w
    return strength_polarity_to_weight(strength, polarity)


def weight_label(weight: float) -> str:
    return SCALE_LABELS.get(normalize_weight(weight), "")
