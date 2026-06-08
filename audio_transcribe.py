"""Gemini API audio transcription for CH-D channel."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from workflow import ProgressCallback, emit

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
# Inline request limit is 20 MB total; use Files API above this threshold.
FILES_API_THRESHOLD = 15 * 1024 * 1024

TRANSCRIBE_PROMPT = """Transcribe the spoken content in this audio accurately.
Return ONLY the transcribed text as plain text — no commentary, labels, or markdown.
Use proper punctuation and sentence boundaries (. ! ?).
Preserve the original language spoken (do not translate)."""

MIME_SUFFIX = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
}


def gemini_api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def gemini_model() -> str:
    return (os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()


def gemini_configured() -> bool:
    return bool(gemini_api_key())


def _client() -> genai.Client:
    key = gemini_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    return genai.Client(api_key=key)


def _suffix_for_mime(mime_type: str) -> str:
    base = (mime_type or "").split(";")[0].strip().lower()
    return MIME_SUFFIX.get(base, ".bin")


def transcribe_audio(
    audio_bytes: bytes,
    *,
    mime_type: str,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not audio_bytes:
        raise ValueError("Empty audio payload.")

    mime = (mime_type or "audio/webm").split(";")[0].strip().lower()
    emit(
        on_progress,
        "transcribe",
        "running",
        {"bytes": len(audio_bytes), "mime": mime},
    )

    client = _client()
    model = gemini_model()

    if len(audio_bytes) > FILES_API_THRESHOLD:
        suffix = _suffix_for_mime(mime)
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            uploaded = client.files.upload(
                file=tmp_path,
                config={"mime_type": mime},
            )
            contents: list[Any] = [TRANSCRIBE_PROMPT, uploaded]
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)
    else:
        contents = [
            TRANSCRIBE_PROMPT,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime),
        ]

    response = client.models.generate_content(model=model, contents=contents)
    text = (response.text or "").strip()

    if len(text) < 20:
        emit(
            on_progress,
            "transcribe",
            "error",
            {"reason": "transcript too short", "length": len(text)},
        )
        raise ValueError(
            f"Transcript too short ({len(text)} chars). "
            "Need at least 20 characters for analysis."
        )

    emit(
        on_progress,
        "transcribe",
        "done",
        {"chars": len(text), "model": model},
    )
    return {"transcript": text, "model": model, "chars": len(text)}
