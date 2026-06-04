# Analysis methods

All three analyses use the **same input**: AI-extracted thematic concept codes per sentence (not raw words). Input text in any language is **translated to English** first; translation, cleaning, and codes are all English. Vocabulary is filtered by minimum frequency (`min_freq`).

**Unit of analysis:** one sentence = one stanza.

---

## Co-occurrence

**Question:** Which concepts appear together in the same sentence?

**Procedure:**

1. For each sentence, take the set of active concepts.
2. For every unordered pair (A, B) in that set, increment matrix[A, B] and matrix[B, A].
3. Diagonal stays zero (no self-loops).

**Matrix:** symmetric counts ≥ 0 on off-diagonal pairs only; diagonal = 0.

**Graph:** an edge exists for every pair with co-occurrence count > 0.

**Interpretation:** local, utterance-level association—what is mentioned together in one breath.

---

## Semantic

**Question:** Which concepts appear in similar contexts across the text?

**Procedure:**

1. Treat each sentence as a “document” containing its concept codes.
2. Build a TF‑IDF vector per concept across sentences (each concept’s profile of where it shows up).
3. Compute **cosine similarity** between every pair of concept profiles.
4. Diagonal set to 0 (no self-loops; perfect self-similarity is excluded).

**Matrix:** off-diagonal similarity in [0, 1]; diagonal = 0.

**Graph:** keeps the strongest off-diagonal links (similarity ≥ median of candidates, capped for readability).

**Interpretation:** distributional / paradigmatic similarity—concepts that “keep similar company” across the corpus, even if they never share a sentence.

---

## Epistemic (ENA-style)

**Question:** Which concept links are stronger or weaker than we would expect by chance, including short-range discourse flow?

**Procedure:**

1. **Concurrent links:** same as co-occurrence pairs within a sentence (weight 1).
2. **Lagged links:** for each pair of consecutive sentences, link every concept in sentence *t* to every concept in sentence *t+1* (weight 0.5; no self-loops across the lag).
3. Sum into a raw co-activation matrix.
4. **Center (ENA-style):** subtract expected counts:  
   `expected[i,j] = (row_sum[i] × col_sum[j]) / total`  
   `centered[i,j] = raw[i,j] − expected[i,j]`

**Matrix:** can be positive or negative.

**Graph:** edges for large |centered| values; green = above expected, red = below expected.

**Interpretation:** epistemic coupling—co-activation and sequential flow, relative to overall concept frequency. Positive ties are “over-connected”; negative ties are “under-connected” given how often each concept appears.

---

## Shared pipeline

```
Text (any language) → English translation (per sentence)
     → AI English concept codes (per sentence) → vocabulary (min frequency)
     → three statistical matrices → base graphs
     → AI direction (a→b, b→a, a↔b) + polarity (±) from English text
     → directed signed matrices + network graphs + XLSX export
```
