"""Language detection and conditional translation."""

from __future__ import annotations

from typing import Any

from langdetect import DetectorFactory, LangDetectException, detect_langs

from ai_preprocess import translate_sentences_to_english
from workflow import ProgressCallback, emit

DetectorFactory.seed = 0

_ENGLISH_CODES = frozenset({"en"})


def detect_language(text: str) -> dict[str, Any]:
    """Detect primary language of text. Returns code, name hint, is_english."""
    sample = (text or "").strip()[:8000]
    if not sample:
        return {"code": "unknown", "name": "unknown", "is_english": False, "confidence": 0.0}

    try:
        hits = detect_langs(sample)
        if not hits:
            return {"code": "unknown", "name": "unknown", "is_english": False, "confidence": 0.0}
        top = hits[0]
        code = top.lang.lower()
        return {
            "code": code,
            "name": code,
            "is_english": code in _ENGLISH_CODES,
            "confidence": round(float(top.prob), 3),
        }
    except LangDetectException:
        return {"code": "unknown", "name": "unknown", "is_english": False, "confidence": 0.0}


def prepare_english_sentences(
    sentences: list[str],
    *,
    client=None,
    model: str | None = None,
    on_progress: ProgressCallback | None = None,
    progress_ctx: dict[str, Any] | None = None,
    language_info: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """
    Return English sentences. Skips translation when language is English.
    """
    ctx = dict(progress_ctx or {})
    lang = language_info or detect_language(" ".join(sentences))
    ctx["language"] = lang.get("code")
    ctx["is_english"] = lang.get("is_english")

    if lang.get("is_english"):
        emit(on_progress, "translate", "done", {**ctx, "skipped": True, "sentences": len(sentences)})
        return list(sentences), {
            "detected": lang.get("code", "en"),
            "translated": False,
            "confidence": lang.get("confidence"),
        }

    emit(on_progress, "translate", "running", {**ctx, "sentences": len(sentences)})
    english = translate_sentences_to_english(
        sentences,
        client=client,
        model=model,
        on_progress=on_progress,
        progress_ctx=ctx,
    )
    emit(on_progress, "translate", "done", {**ctx, "skipped": False, "sentences": len(english)})
    return english, {
        "detected": lang.get("code", "unknown"),
        "translated": True,
        "confidence": lang.get("confidence"),
    }
