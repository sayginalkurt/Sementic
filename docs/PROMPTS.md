# AI prompts

All OpenAI prompts used by the web application. Implemented in `ai_preprocess.py` (translation + concept coding) and `ai_relations.py` (direction + polarity).

**API settings (shared):** `response_format={"type": "json_object"}`, `temperature=0.1`  
**Model:** `OPENAI_MODEL` env var, default `gpt-4o-mini`

---

## 1. Translation (batch)

**Source:** `TRANSLATION_SYSTEM_PROMPT`, `TRANSLATION_USER_TEMPLATE`  
**When:** First pass for each batch (≤18 sentences).

### System

```
You are a professional translator for qualitative research texts.
Translate each input sentence into clear, natural English. Preserve meaning, tone, and granularity.
Do not merge, split, or drop sentences. Do not add commentary.
Return JSON only: {"sentences": ["...", ...]}
The output array MUST have exactly the same length and order as the input array.
```

### User

```
Translate exactly {count} sentences to English.

Return JSON: {"sentences": ["...", ...]} with EXACTLY {count} strings, same order as input (index 0 = sentence 1).

Input JSON array:
{sentences_json}
```

**Variables:** `{count}` — batch size; `{sentences_json}` — JSON array of source sentences.

---

## 2. Translation (retry)

**Source:** `TRANSLATION_RETRY_TEMPLATE`  
**When:** Batch response length does not match input.

### User

```
Your last answer had {got} strings but MUST have exactly {count}.

Translate each sentence below to English. Return EXACTLY {count} strings in the same order.

Input JSON array:
{sentences_json}
```

**Variables:** `{got}`, `{count}`, `{sentences_json}`

---

## 3. Translation (single-sentence fallback)

**Source:** `TRANSLATE_ONE_SYSTEM`  
**When:** Batch + retry still return wrong count; one call per missing sentence.

### System

```
Translate the given sentence to English. Return JSON only: {"text": "..."}
```

### User

The raw sentence text (no template).

**Expected JSON:** `{"text": "..."}`

---

## 4. Thematic concept extraction

**Source:** `CONCEPT_SYSTEM_PROMPT`, `CONCEPT_USER_TEMPLATE`  
**When:** Once per analyze, on joined English sentences.

### System

```
You are an expert coder extracting EPISTEMIC / THEMATIC CONCEPT codes from qualitative research text in English.

CRITICAL: Every concept code MUST be an English lemma (Latin alphabet a-z only). Never output Turkish or any non-English word, even if it appeared in the source.

Task: For each sentence, list concept lemmas that represent the ideas expressed—like answers to "What comes to mind about Amazon?" (meaning units, not grammar).

EXTRACT (examples):
- "When I think of Amazon, product variety comes to mind" → ["amazon", "product", "variety"]
- "Fast delivery builds trust" → ["delivery", "speed", "trust"]
- "The return process is easy" → ["return", "process", "ease"]

DO NOT EXTRACT:
- Conjunctions / prepositions / fillers: and, or, the, of, for, with, but, because …
- Pronouns / demonstratives: this, that, it, one, someone, people …
- Grammatical fragments: comes, mind, being, having, very, really …
- Time / quantity fluff: many, some, often, always …
- Words that are not standalone thematic codes even if they appear in the text

Rules:
- Lowercase English lemmas (1–2 meaningful words; no unnecessary compounds)
- One entry per repeated concept per sentence
- Empty sentence → []
- Return valid JSON only
```

### User

```
Read the English text sentence by sentence. Extract only thematic concept codes (no grammar/fillers).

JSON:
{
  "sentences": [
    ["concept1", "concept2"],
    ...
  ]
}

Sentence count and order must match the input ({count} sentences).

Text:
---
{text}
---
```

**Variables:** `{count}` — number of sentences; `{text}` — English lines joined with newlines (truncated at 120,000 chars).

**Expected JSON:** `{"sentences": [["lemma", ...], ...]}`

### Post-processing (not a prompt)

Concepts are filtered in code via `CONCEPT_BLOCKLIST` and `ENGLISH_STOPWORDS` (`preprocess.py` / `ai_preprocess.py`). Only `a-z` lemmas pass `is_valid_concept()`.

---

## 5. Directed relations and polarity

**Source:** `RELATION_SYSTEM_PROMPT`, `RELATION_USER_TEMPLATE`, `KIND_NOTES`  
**When:** Per analysis type (`cooccurrence`, `semantic`, `epistemic`), batched concept pairs (≤24 pairs per call).

### System

```
You infer directed semantic relations between concept pairs using ONLY the provided English qualitative research text.

For each pair, concepts are given as (a, b) in alphabetical order. Return for each:
- direction:
  - "a_to_b" — the text supports A → B (A precedes, enables, leads to, or is prerequisite for B)
  - "b_to_a" — the text supports B → A
  - "mutual" — reciprocal / bidirectional link (A ↔ B)
- polarity:
  - "positive" — supportive, aligned, coherent association in context
  - "negative" — tension, opposition, trade-off, inhibition, or conflict between concepts

Return JSON only:
{"relations": [{"a": "...", "b": "...", "direction": "a_to_b|b_to_a|mutual", "polarity": "positive|negative"}]}
Use exact concept strings from the input. One object per pair listed.
```

### User

```
Analysis type: {kind}
Context: {kind_note}

English text:
---
{text}
---

Concept pairs to label (alphabetical a, b):
{pairs_json}
```

**Variables:**

| Variable | Description |
|----------|-------------|
| `{kind}` | `cooccurrence`, `semantic`, or `epistemic` |
| `{kind_note}` | See table below |
| `{text}` | Full English source (truncated at 80,000 chars) |
| `{pairs_json}` | `[{"a": "...", "b": "..."}, ...]` |

### Analysis context (`KIND_NOTES`)

| `kind` | `kind_note` |
|--------|-------------|
| `cooccurrence` | Pairs co-occur in the same sentence; infer causal or logical direction from discourse, not just proximity. |
| `semantic` | Pairs are distributionally similar; infer how meanings relate directionally in the argument. |
| `epistemic` | ENA-style association; infer epistemic flow (what supports or constrains what). |

**Expected JSON:**

```json
{
  "relations": [
    {"a": "concept_a", "b": "concept_b", "direction": "a_to_b", "polarity": "positive"}
  ]
}
```

**Defaults if a pair is missing from the response:** `direction: "mutual"`, `polarity: "positive"`.

---

## Call order (typical web analyze)

1. Translation batches → optional retry → optional per-sentence fallback  
2. Concept extraction (one call)  
3. Relation inference × 3 analysis types (multiple batches per type)

See [FLOW.md](FLOW.md) for the full pipeline.

---

## 6. FCM — concept merge (hybrid)

**Source:** `concept_hybrid.py` — `CONCEPT_MERGE_SYSTEM`, `CONCEPT_MERGE_USER`  
**When:** After spaCy phrase extraction + embedding clustering.

Groups phrase clusters into higher-level English concept labels. Maps every phrase to a `concept_id`.

---

## 7. FCM — polarity context

**Source:** `fcm_inference.py` — `POLARITY_SYSTEM`, `POLARITY_USER`  
**When:** After concept merge, before edge inference.

Returns `review_tone` and per-concept `concept_valence` with ambivalence notes (e.g. small size + good organization → navigability).

---

## 8. FCM — causal edges

**Source:** `fcm_inference.py` — `FCM_EDGE_SYSTEM`, `FCM_EDGE_USER`  
**When:** Final LLM step; uses concepts, phrase map, polarity context, and full English text.

Each edge: `source`, `target`, `weight` (−2..+2), `strength`, `polarity`, `evidence_sentence`, `analyst_note`.

**Call order (FCM):**

1. Language detect (no LLM)
2. Translation batches (if not English)
3. spaCy phrases + OpenAI embeddings (no chat)
4. Concept merge (one chat call)
5. Polarity context (one chat call)
6. FCM edges (one chat call)
