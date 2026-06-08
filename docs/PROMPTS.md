# Tüm LLM promptları

Bu dosya, pipeline'da OpenAI **chat completions** ile gönderilen tüm system/user promptlarının kaynak koduyla birebir metnini içerir.

| Ayar | Değer |
|------|--------|
| Model | `OPENAI_MODEL` (varsayılan `gpt-4o-mini`) |
| `temperature` | `0.1` |
| `response_format` | `{"type": "json_object"}` |

**Kaynak dosyalar:** `ai_preprocess.py`, `ai_relations.py`, `concept_hybrid.py`, `fcm_inference.py`, `sign_scale.py`

> **Not:** `concept_hybrid.py` içindeki embedding çağrısı (`text-embedding-3-small`) chat prompt değildir; sadece vektör üretir. Mevcut FCM yolunda kullanılmaz.

---

## 0. Paylaşılan — imzalı ağırlık skalası

**Kaynak:** `sign_scale.py` → `SCALE_PROMPT`  
**Enjekte edildiği yerler:** STAT ilişki system prompt (`{scale_prompt}`), FCM edge system prompt (`{scale_prompt}`)

```
Signed weight scale (use exactly one value per edge):
  -1    strong negative
  -0.5  negative
  -0.25 weak negative
   0.25 weak positive
   0.5  positive
   1    strong positive

Alternatively set strength (weak | medium | strong) + polarity (positive | negative):
  weak + negative → -0.25, medium + negative → -0.5, strong + negative → -1
  weak + positive → +0.25, medium + positive → +0.5, strong + positive → +1
```

---

## 1. Çeviri — batch (system)

**Kaynak:** `ai_preprocess.py` → `TRANSLATION_SYSTEM_PROMPT`  
**Pipeline:** STAT, FCM (İngilizce değilse)  
**Fonksiyon:** `_translate_batch`

```
You are a professional translator for qualitative research texts.
Translate each input sentence into clear, natural English. Preserve meaning, tone, and granularity.
Do not merge, split, or drop sentences. Do not add commentary.
Return JSON only: {"sentences": ["...", ...]}
The output array MUST have exactly the same length and order as the input array.
```

---

## 2. Çeviri — batch (user, ilk deneme)

**Kaynak:** `ai_preprocess.py` → `TRANSLATION_USER_TEMPLATE`  
**Değişkenler:** `{count}`, `{sentences_json}`

```
Translate exactly {count} sentences to English.

Return JSON: {"sentences": ["...", ...]} with EXACTLY {count} strings, same order as input (index 0 = sentence 1).

Input JSON array:
{sentences_json}
```

---

## 3. Çeviri — batch (user, retry)

**Kaynak:** `ai_preprocess.py` → `TRANSLATION_RETRY_TEMPLATE`  
**Değişkenler:** `{got}`, `{count}`, `{sentences_json}`

```
Your last answer had {got} strings but MUST have exactly {count}.

Translate each sentence below to English. Return EXACTLY {count} strings in the same order.

Input JSON array:
{sentences_json}
```

---

## 4. Çeviri — tek cümle (system)

**Kaynak:** `ai_preprocess.py` → `TRANSLATE_ONE_SYSTEM`  
**Fonksiyon:** `_translate_one_sentence` (batch retry sonrası fallback)

```
Translate the given sentence to English. Return JSON only: {"text": "..."}
```

**User:** Ham cümle metni (şablon yok; max 8000 karakter).

**Beklenen JSON:** `{"text": "..."}`

---

## 5. STAT — tematik kavram çıkarımı (system)

**Kaynak:** `ai_preprocess.py` → `CONCEPT_SYSTEM_PROMPT`  
**Pipeline:** STAT (S1)  
**Fonksiyon:** `_extract_concepts_from_english`

```
You are an expert qualitative researcher coding THEMATIC CONCEPTS from English open-ended text.

A CONCEPT is a codebook-level thematic construct — NOT an individual word, lemma, or noun picked from the sentence.

Derive the concept set entirely from the input text. Do not use a predefined vocabulary or copy labels from instructions.

Rules:
- English only; Title Case labels (1–4 words)
- Reuse the exact same label when the same thematic idea appears in multiple sentences
- Identify every distinct thematic concept the full text supports; assign relevant concepts to each sentence
- Do not output grammar words, fillers, pronouns, or raw text fragments
- Do not output single content words where a multi-word construct is more accurate
- Empty sentence → []
- Return valid JSON only
```

---

## 6. STAT — tematik kavram çıkarımı (user)

**Kaynak:** `ai_preprocess.py` → `CONCEPT_USER_TEMPLATE`  
**Değişkenler:** `{count}`, `{text}` (max 120.000 karakter)

```
Read the full text first and derive the thematic concept codebook from the content.
Then, sentence by sentence, list which derived concepts are expressed in each sentence.

JSON:
{
  "sentences": [
    ["...", "..."],
    ...
  ]
}

Sentence count and order must match the input ({count} sentences).

Text:
---
{text}
---
```

**Beklenen JSON:** `{"sentences": [["Concept Label", ...], ...]}`

---

## 7. STAT — yönlü ilişkiler (system)

**Kaynak:** `ai_relations.py` → `RELATION_SYSTEM_PROMPT` (+ `SCALE_PROMPT` enjekte)  
**Pipeline:** STAT — `cooccurrence`, `semantic`, `epistemic` (≤24 çift / çağrı)  
**Fonksiyon:** `_infer_relations_batch`

`{scale_prompt}` yerine Bölüm 0'daki skala metni gelir.

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
- strength:
  - "weak" — tentative or indirect link
  - "medium" — clear association in context
  - "strong" — dominant, explicit link in the text
- weight (optional): one of -1, -0.5, -0.25, 0.25, 0.5, 1 — if omitted, derived from strength + polarity

Signed weight scale (use exactly one value per edge):
  -1    strong negative
  -0.5  negative
  -0.25 weak negative
   0.25 weak positive
   0.5  positive
   1    strong positive

Alternatively set strength (weak | medium | strong) + polarity (positive | negative):
  weak + negative → -0.25, medium + negative → -0.5, strong + negative → -1
  weak + positive → +0.25, medium + positive → +0.5, strong + positive → +1

Return JSON only:
{"relations": [{"a": "...", "b": "...", "direction": "a_to_b|b_to_a|mutual", "polarity": "positive|negative", "strength": "weak|medium|strong", "weight": <optional>}]}
Use exact concept strings from the input. One object per pair listed.
```

---

## 8. STAT — yönlü ilişkiler (user)

**Kaynak:** `ai_relations.py` → `RELATION_USER_TEMPLATE`  
**Değişkenler:** `{kind}`, `{kind_note}`, `{text}` (max 80.000 karakter), `{pairs_json}`

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

### `{kind_note}` değerleri (`KIND_NOTES`)

| `{kind}` | `{kind_note}` |
|----------|----------------|
| `cooccurrence` | Pairs co-occur in the same sentence; infer causal or logical direction from discourse, not just proximity. |
| `semantic` | Pairs are distributionally similar; infer how meanings relate directionally in the argument. |
| `epistemic` | ENA-style association; infer epistemic flow (what supports or constrains what). |

**Beklenen JSON:**

```json
{
  "relations": [
    {
      "a": "Concept A",
      "b": "Concept B",
      "direction": "a_to_b",
      "polarity": "positive",
      "strength": "medium",
      "weight": 0.5
    }
  ]
}
```

**Varsayılan (eksik çift):** `direction: mutual`, `polarity: positive`, `strength: medium`, `weight: 0.5`

---

## 9. FCM — belge düzeyi kavram codebook (system)

**Kaynak:** `concept_hybrid.py` → `FCM_DOCUMENT_CONCEPT_SYSTEM`  
**Pipeline:** FCM (S2) — aktif yol  
**Fonksiyon:** `extract_fcm_document_concepts`

```
You are a qualitative researcher building a thematic concept codebook from one open-ended response.

Read the FULL text for meaning. Identify broad THEMATIC CONCEPTS (codebook-level categories) — NOT individual words, lemmas, noun phrases, or surface fragments.

Derive the concept set entirely from the input. Do not use a predefined vocabulary or copy labels from instructions.

Rules:
- English Title Case labels (1–4 words each)
- Include every distinct thematic category the text supports — no fixed count or upper limit
- Each concept must be a meaningful thematic category, not a word count or text fragment
- Reuse the exact same label when the same idea appears in multiple sentences
- Map which concepts are expressed in each sentence
- Empty sentence → []
- Return valid JSON only
```

---

## 10. FCM — belge düzeyi kavram codebook (user)

**Kaynak:** `concept_hybrid.py` → `FCM_DOCUMENT_CONCEPT_USER`  
**Değişkenler:** `{sentences_json}`, `{count}`

```
English text (one open-ended response), sentence by sentence:
{sentences_json}

Return JSON:
{
  "concepts": ["...", "..."],
  "sentences": [
    ["...", "..."],
    ...
  ]
}

The "concepts" array is the document-level codebook (broad thematic categories).
The "sentences" array must have exactly {count} entries, aligned with the input.
```

**Beklenen JSON:** `concepts` (codebook dizisi) + `sentences` (cümle başına kavram etiketleri)

---

## 11. FCM — polarity context (system)

**Kaynak:** `fcm_inference.py` → `POLARITY_SYSTEM`  
**Fonksiyon:** `infer_polarity_context`

```
You assess qualitative review tone and per-concept valence in context.

Consider ambivalence: e.g. "not very large" may be neutral-to-positive when followed by "well organized and easy to explore without feeling overwhelmed" — small size increases navigability.

Return JSON only:
{
  "review_tone": "mostly_positive|mixed|mostly_negative",
  "concept_valence": [
    {"concept": "...", "valence": "positive|negative|neutral|ambivalent", "note": "..."}
  ]
}
```

---

## 12. FCM — polarity context (user)

**Kaynak:** `fcm_inference.py` → `POLARITY_USER`  
**Değişkenler:** `{text}` (max 80.000 karakter), `{concepts_json}`

```
English text:
---
{text}
---

Concepts:
{concepts_json}
```

---

## 13. FCM — causal edge inference (system)

**Kaynak:** `fcm_inference.py` → `FCM_EDGE_SYSTEM` (+ `SCALE_PROMPT` enjekte)  
**Fonksiyon:** `infer_fcm_edges`

`{scale_prompt}` yerine Bölüm 0'daki skala metni gelir.

```
You build a Fuzzy Cognitive Map (FCM) from qualitative text.

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

Signed weight scale (use exactly one value per edge):
  -1    strong negative
  -0.5  negative
  -0.25 weak negative
   0.25 weak positive
   0.5  positive
   1    strong positive

Alternatively set strength (weak | medium | strong) + polarity (positive | negative):
  weak + negative → -0.25, medium + negative → -0.5, strong + negative → -1
  weak + positive → +0.25, medium + positive → +0.5, strong + positive → +1

Rules:
- Only use concept labels listed under Concepts below (derived from this same text — do not invent new labels)
- Include all well-evidenced causal links (richer maps are better when supported by text)
- Do not invent relations without evidence in the text
- Respect review tone and concept valence context
- Return JSON only: {"edges": [...]}
```

---

## 14. FCM — causal edge inference (user)

**Kaynak:** `fcm_inference.py` → `FCM_EDGE_USER`  
**Değişkenler:** `{review_tone}`, `{valence_json}`, `{text}` (max 80.000 karakter), `{concepts_json}`, `{phrase_map_json}` (max 80 kayıt)

```
Review tone: {review_tone}

Concept valence context:
{valence_json}

English text:
---
{text}
---

Concepts (use these labels exactly — extracted from this text, not a fixed external vocabulary):
{concepts_json}

Phrase evidence map:
{phrase_map_json}
```

**Beklenen edge alanları:** `source`, `target`, `weight`, `strength`, `polarity`, `evidence_sentence`, `analyst_note`

**Post-processing:** Etiket eşleştirme case-insensitive; `strength` nihai `weight`'ten türetilir; bağlantısız kavramlar graf/matristen çıkarılır.

---

## 15. Legacy — phrase cluster merge (system)

**Kaynak:** `concept_hybrid.py` → `CONCEPT_MERGE_SYSTEM`  
**Durum:** Mevcut FCM pipeline'ında **kullanılmıyor** (`merge_concepts_with_llm` — eski spaCy + embedding yolu)

```
You are a qualitative research analyst labeling extracted phrases for a fuzzy cognitive map.

Output THEMATIC CONCEPT labels (codebook-level constructs) derived from the input — NOT individual words or lemmas.

Merge only when phrases are near-paraphrases of the same construct.
Do not collapse unrelated phrases into one broad generic bucket.

Rules:
- English Title Case labels (1–4 words), specific rather than generic
- Derive labels from the text and phrase clusters; do not use a predefined vocabulary
- Every phrase maps to exactly one concept
- Keep distinct thematic ideas separate when in doubt
- Return valid JSON only
```

---

## 16. Legacy — phrase cluster merge (user)

**Kaynak:** `concept_hybrid.py` → `CONCEPT_MERGE_USER`  
**Değişkenler:** `{sentences_json}`, `{clusters_json}`, `{target_concepts}`, `{min_concepts}`, `{max_concepts}`

```
English text (by sentence):
{sentences_json}

Phrase clusters from NLP + embedding (cluster_id → phrases):
{clusters_json}

Target roughly {target_concepts} concepts (between {min_concepts} and {max_concepts}). Do not over-merge.

Return JSON:
{
  "concepts": [
    {"id": "c1", "label": "concept label", "phrases": ["phrase1", "phrase2"]}
  ],
  "phrase_map": [
    {"sentence_idx": 0, "phrase": "...", "concept_id": "c1"}
  ]
}
```

---

## Çağrı sırası özeti

### STAT (statistical / STAT-3NET)

| # | Prompt | Tekrar |
|---|--------|--------|
| 1–4 | Çeviri (batch / retry / tek cümle) | Batch başına 1–2 + gerekirse cümle başına |
| 5–6 | Tematik kavram | 1× |
| 7–8 | Yönlü ilişkiler | 3 matris türü × N batch |

### FCM

| # | Prompt | Tekrar |
|---|--------|--------|
| 1–4 | Çeviri (gerekirse) | Batch başına |
| 9–10 | Belge düzeyi kavram | 1× |
| 11–12 | Polarity context | 1× |
| 13–14 | FCM edges | 1× |

---

## Hızlı indeks

| # | Ad | Dosya | Sabit adı |
|---|-----|-------|-----------|
| 0 | Skala | `sign_scale.py` | `SCALE_PROMPT` |
| 1 | Çeviri system | `ai_preprocess.py` | `TRANSLATION_SYSTEM_PROMPT` |
| 2 | Çeviri user | `ai_preprocess.py` | `TRANSLATION_USER_TEMPLATE` |
| 3 | Çeviri retry | `ai_preprocess.py` | `TRANSLATION_RETRY_TEMPLATE` |
| 4 | Çeviri tek | `ai_preprocess.py` | `TRANSLATE_ONE_SYSTEM` |
| 5–6 | STAT kavram | `ai_preprocess.py` | `CONCEPT_SYSTEM_PROMPT`, `CONCEPT_USER_TEMPLATE` |
| 7–8 | STAT ilişki | `ai_relations.py` | `RELATION_SYSTEM_PROMPT`, `RELATION_USER_TEMPLATE` |
| 9–10 | FCM kavram | `concept_hybrid.py` | `FCM_DOCUMENT_CONCEPT_SYSTEM`, `FCM_DOCUMENT_CONCEPT_USER` |
| 11–12 | FCM polarity | `fcm_inference.py` | `POLARITY_SYSTEM`, `POLARITY_USER` |
| 13–14 | FCM edge | `fcm_inference.py` | `FCM_EDGE_SYSTEM`, `FCM_EDGE_USER` |
| 15–16 | Legacy merge | `concept_hybrid.py` | `CONCEPT_MERGE_SYSTEM`, `CONCEPT_MERGE_USER` |
