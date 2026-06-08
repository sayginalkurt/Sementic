"""OpenAI: translate to English, then thematic concept extraction (network codes)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from preprocess import ENGLISH_STOPWORDS, normalize_text, sentences_from_text

# Function words / fillers that must not enter matrices as standalone concepts
CONCEPT_BLOCKLIST = frozenset(
    """
    about above across after against along amid among around before behind below
    comes came coming goes went going gets got getting makes made making says said
    saying thinks thought knows knew sees saw wants needs uses used using takes took
    gives gave tells feels seemed looked becomes there their they're its it's
    upon onto unto thee thy thine whilst wherein whereby something someone anybody
    people person humans being beings really quite perhaps maybe
    """.split()
) | ENGLISH_STOPWORDS

TRANSLATION_SYSTEM_PROMPT = """You are a professional translator for qualitative research texts.
Translate each input sentence into clear, natural English. Preserve meaning, tone, and granularity.
Do not merge, split, or drop sentences. Do not add commentary.
Return JSON only: {"sentences": ["...", ...]}
The output array MUST have exactly the same length and order as the input array."""

TRANSLATION_USER_TEMPLATE = """Translate exactly {count} sentences to English.

Return JSON: {{"sentences": ["...", ...]}} with EXACTLY {count} strings, same order as input (index 0 = sentence 1).

Input JSON array:
{sentences_json}"""

TRANSLATION_RETRY_TEMPLATE = """Your last answer had {got} strings but MUST have exactly {count}.

Translate each sentence below to English. Return EXACTLY {count} strings in the same order.

Input JSON array:
{sentences_json}"""

TRANSLATE_ONE_SYSTEM = """Translate the given sentence to English. Return JSON only: {"text": "..."}"""

CONCEPT_SYSTEM_PROMPT = """You are an expert qualitative researcher coding THEMATIC CONCEPTS from English open-ended text.

A CONCEPT is a codebook-level thematic construct — NOT an individual word, lemma, or noun picked from the sentence.

Derive the concept set entirely from the input text. Do not use a predefined vocabulary or copy labels from instructions.

Rules:
- English only; Title Case labels (1–4 words)
- Reuse the exact same label when the same thematic idea appears in multiple sentences
- Identify a concise set of distinct concepts for the full text; assign relevant concepts to each sentence
- Do not output grammar words, fillers, pronouns, or raw text fragments
- Do not output single content words where a multi-word construct is more accurate
- Empty sentence → []
- Return valid JSON only"""

CONCEPT_USER_TEMPLATE = """Read the full text first and derive the thematic concept codebook from the content.
Then, sentence by sentence, list which derived concepts are expressed in each sentence.

JSON:
{{
  "sentences": [
    ["...", "..."],
    ...
  ]
}}

Sentence count and order must match the input ({count} sentences).

Text:
---
{text}
---"""

# Small batches — large arrays cause the model to drop or merge sentences
_TRANSLATE_BATCH_MAX_SENTENCES = 18
_TRANSLATE_BATCH_MAX_CHARS = 12_000
_NON_ENGLISH_CHARS = re.compile(r"[^a-zA-Z0-9'\-/ ]")
_SMALL_WORDS = frozenset({"of", "and", "or", "for", "to", "in", "on", "at", "by", "the", "a", "an"})


def normalize_concept_label(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw.strip())
    if not s:
        return ""
    words = []
    for word in s.split(" "):
        if not word:
            continue
        if "'" in word:
            parts = word.split("'")
            words.append("'".join(p[:1].upper() + p[1:].lower() if p else "" for p in parts))
        elif word.lower() in _SMALL_WORDS and words:
            words.append(word.lower())
        else:
            words.append(word[:1].upper() + word[1:].lower())
    return " ".join(words)


def is_valid_concept(label: str) -> bool:
    s = normalize_concept_label(label)
    if len(s) < 2 or len(s) > 48:
        return False
    if _NON_ENGLISH_CHARS.search(s):
        return False
    if not re.match(r"^[A-Za-z][A-Za-z0-9'\-/ ]*[A-Za-z0-9']$", s):
        return False
    low = s.lower()
    if " " not in s and low in CONCEPT_BLOCKLIST:
        return False
    return True


def filter_concept_list(tokens: list[str]) -> list[str]:
    row: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not isinstance(token, str):
            continue
        w = normalize_concept_label(token)
        key = w.lower()
        if is_valid_concept(w) and key not in seen:
            seen.add(key)
            row.append(w)
    return row


def _openai_client(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> OpenAI:
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Create a .env file or set the environment variable."
        )
    return OpenAI(api_key=key, base_url=base_url or os.environ.get("OPENAI_BASE_URL"))


def _chat_json(
    client: OpenAI,
    model: str,
    *,
    system: str,
    user: str,
    temperature: float = 0.1,
) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw.strip())
    if not isinstance(data, dict):
        raise ValueError("Model response is not a JSON object.")
    return data


def _translation_batches(sentences: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for sent in sentences:
        sent_len = len(sent) + 4
        over_chars = current and size + sent_len > _TRANSLATE_BATCH_MAX_CHARS
        over_count = len(current) >= _TRANSLATE_BATCH_MAX_SENTENCES
        if current and (over_chars or over_count):
            batches.append(current)
            current = []
            size = 0
        current.append(sent)
        size += sent_len
    if current:
        batches.append(current)
    return batches


def _sentences_from_translation_json(data: dict[str, Any]) -> list[str]:
    if "sentences" not in data:
        raise ValueError("Translation response missing 'sentences'.")
    out = data["sentences"]
    if not isinstance(out, list):
        raise ValueError("'sentences' must be an array.")
    return [str(item).strip() if isinstance(item, str) else "" for item in out]


def _translate_one_sentence(
    client: OpenAI,
    model: str,
    sentence: str,
) -> str:
    data = _chat_json(
        client,
        model,
        system=TRANSLATE_ONE_SYSTEM,
        user=sentence[:8000],
    )
    text = data.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return sentence


def _translate_batch(
    client: OpenAI,
    model: str,
    batch: list[str],
) -> list[str]:
    """Translate a batch; retry on count mismatch, then fall back per sentence."""
    payload = json.dumps(batch, ensure_ascii=False)
    expected = len(batch)
    last_got = 0

    for attempt in range(2):
        if attempt == 0:
            user = TRANSLATION_USER_TEMPLATE.format(
                count=expected, sentences_json=payload
            )
        else:
            user = TRANSLATION_RETRY_TEMPLATE.format(
                count=expected, got=last_got, sentences_json=payload
            )

        data = _chat_json(
            client,
            model,
            system=TRANSLATION_SYSTEM_PROMPT,
            user=user,
        )
        try:
            translated = _sentences_from_translation_json(data)
        except ValueError:
            translated = []

        last_got = len(translated)
        if last_got == expected:
            return translated

    return [_translate_one_sentence(client, model, s) for s in batch]


def translate_sentences_to_english(
    sentences: list[str],
    *,
    client: OpenAI | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    on_progress=None,
    progress_ctx: dict | None = None,
) -> list[str]:
    """Translate source sentences to English, preserving count and order."""
    if not sentences:
        return []

    chosen_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    oai = client or _openai_client(api_key=api_key, base_url=base_url)

    batches = _translation_batches(sentences)
    english: list[str] = []
    for i, batch in enumerate(batches):
        if on_progress:
            detail = {"batch": i + 1, "batches": len(batches), **(progress_ctx or {})}
            on_progress("translate", "running", detail)
        english.extend(_translate_batch(oai, chosen_model, batch))

    if len(english) != len(sentences):
        raise ValueError(
            f"Full translation length mismatch: expected {len(sentences)}, got {len(english)}."
        )
    return english


def _parse_concepts_json(raw: str) -> list[list[str]]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict) or "sentences" not in data:
        raise ValueError("Concept response missing 'sentences'.")
    sentences = data["sentences"]
    if not isinstance(sentences, list):
        raise ValueError("'sentences' must be an array.")

    return [filter_concept_list(item) if isinstance(item, list) else [] for item in sentences]


def _align_sentence_count(
    concepts: list[list[str]], source_sentences: list[str]
) -> list[list[str]]:
    if len(concepts) == len(source_sentences):
        return concepts
    if len(concepts) > len(source_sentences):
        return concepts[: len(source_sentences)]
    padded = list(concepts)
    while len(padded) < len(source_sentences):
        padded.append([])
    return padded


def _extract_concepts_from_english(
    english_sentences: list[str],
    *,
    client: OpenAI,
    model: str,
) -> list[list[str]]:
    english_text = "\n".join(english_sentences)
    data = _chat_json(
        client,
        model,
        system=CONCEPT_SYSTEM_PROMPT,
        user=CONCEPT_USER_TEMPLATE.format(
            count=len(english_sentences),
            text=english_text[:120000],
        ),
    )
    raw = json.dumps(data)
    concepts = _parse_concepts_json(raw)
    concepts = _align_sentence_count(concepts, english_sentences)
    return [filter_concept_list(c) for c in concepts]


def extract_concepts_with_ai(
    text: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[list[list[str]], list[str], list[str]]:
    """
    Any-language text → English sentences → English thematic concept codes per sentence.
    Network matrices must be built only from this output.
    Returns (concepts_by_sentence, flat_concept_list, english_sentences).
    """
    text = normalize_text(text)
    source_sentences = sentences_from_text(text)
    if not source_sentences:
        raise ValueError("No sentences found in the text.")

    client = _openai_client(api_key=api_key, base_url=base_url)
    chosen_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    english_sentences = translate_sentences_to_english(
        source_sentences, client=client, model=chosen_model
    )
    concepts = _extract_concepts_from_english(
        english_sentences, client=client, model=chosen_model
    )

    non_empty = [c for c in concepts if c]
    if not non_empty:
        raise ValueError("No valid concepts extracted. Check the input text.")

    flat = sorted({w for sent in concepts for w in sent})
    return concepts, flat, english_sentences


def concepts_preview(sentences: list[list[str]], limit: int = 40) -> list[dict[str, Any]]:
    from collections import Counter

    counts = Counter(w for s in sentences for w in s)
    top = counts.most_common(limit)
    return [{"concept": k, "count": v} for k, v in top]
