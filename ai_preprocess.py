"""OpenAI ile Türkçe tematik kavram çıkarımı (ağ analizi kodları)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from preprocess import TURKISH_STOPWORDS, normalize_text, sentences_from_text

# AI sızıntısı: bağlaç, edat, dolgu, dilbilgisel parça (matrise girmemeli)
CONCEPT_BLOCKLIST = frozenset(
    """
    da de di den dan ki mi mu mü mı mı dır dir dur dur denken diye ile ve veya
    için gibi kadar daha en çok az bir bu şu o ne nasıl neden niçin niye
    deyince aklıma aklı gelme gelmek geliyor gelen gibi olan olma olur oluyor
    olmuş olacak oldu olması var yok ise işte yani açıkçası tabii hatta özellikle
    bazen her tüm birçok birkaç sadece ancak fakat ama çünkü eğer sanki zaten
    bile hem hiç hep sonra önce burada orada şimdi ben sen biz siz onlar
    benim senin onun bizim sizin kendi kendim kendini insan insanı insanı
    birisi biri kim kimse şey şeyler şeyi birşey böyle öyle şöyle nasıl ne kadar
    rağmen dolayı göre üzere beri beri beri kadar kadarlık gibi gibi
    mutlaka vardır vardı yoktur ediyor eder etmek yapılan yapıyor yapmak
    olduğu olduğunu olduğum olduğumuz olanlar olarak tarafından tarafı
    """.split()
) | TURKISH_STOPWORDS

SYSTEM_PROMPT = """Sen nitel araştırma metinlerinden EPISTEMİK / TEMATİK KAVRAM kodları çıkaran bir uzman kodlayıcısın.

Görev: Her cümle için, o cümlede geçen fikirleri temsil eden kavram köklerini listele — tıpkı katılımcıya "Amazon deyince aklınıza ne geliyor?" dense çıkacak ANLAM Öğeleri gibi.

NE ÇIKAR (örnekler):
- "Amazon deyince aklıma ürün çeşitliliği geliyor" → ["amazon", "ürün", "çeşitlilik"]
- "Hızlı teslimat güven veriyor" → ["teslimat", "hız", "güven"]
- "İade süreci kolay" → ["iade", "süreç", "kolaylık"]

NE ÇIKARMA (kesinlikle yasak):
- Bağlaç / edat / ünlem: da, de, diye, ki, için, gibi, ile, ve, ama, çünkü …
- Zamir / gösterir: bu, şu, o, bir, ben, sen, insan, birisi …
- Dilbilgisel parça: deyince, aklıma, geliyor, olan, olarak, için, hatta …
- Zaman / miktar dolgusu: çok, daha, bazen, her, tüm …
- Metinde geçse bile anlamsız tek başına kod olmayan sözcükler

Kurallar:
- Türkçe küçük harf, lemma (kök): alışveriş, teslimat, güven, amazon
- Her kavram tek başına kod olmalı (1–2 anlamlı kelime; gereksiz sözcük birleştirme)
- Aynı cümlede tekrarı bir kez yaz
- Cümlede kod yoksa []
- YALNIZCA geçerli JSON döndür"""

USER_TEMPLATE = """Metni cümle cümle oku. Her cümle için yalnızca tematik kavram kodlarını çıkar (bağlaç/dolgu değil).

JSON:
{{
  "sentences": [
    ["kavram1", "kavram2"],
    ...
  ]
}}

Cümle sayısı ve sırası metinle aynı olmalı.

Metin:
---
{text}
---"""


def is_valid_concept(word: str) -> bool:
    w = word.strip().lower()
    if len(w) < 2:
        return False
    if w in CONCEPT_BLOCKLIST:
        return False
    # Tek harfli ek kalıntıları (da/de vb.)
    if w in {"da", "de", "di", "ki", "mi", "mu", "mü", "mı", "ta", "te"}:
        return False
    return True


def filter_concept_list(tokens: list[str]) -> list[str]:
    row: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not isinstance(token, str):
            continue
        w = token.strip().lower()
        if is_valid_concept(w) and w not in seen:
            seen.add(w)
            row.append(w)
    return row


def _parse_concepts_json(raw: str) -> list[list[str]]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict) or "sentences" not in data:
        raise ValueError("Yanıtta 'sentences' alanı yok.")
    sentences = data["sentences"]
    if not isinstance(sentences, list):
        raise ValueError("'sentences' bir dizi olmalı.")

    return [filter_concept_list(item) if isinstance(item, list) else [] for item in sentences]


def _align_sentence_count(
    concepts: list[list[str]], source_sentences: list[str]
) -> list[list[str]]:
    """Model farklı cümle sayısı döndürürse hizala."""
    if len(concepts) == len(source_sentences):
        return concepts
    if len(concepts) > len(source_sentences):
        return concepts[: len(source_sentences)]
    padded = list(concepts)
    while len(padded) < len(source_sentences):
        padded.append([])
    return padded


def extract_concepts_with_ai(
    text: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[list[list[str]], list[str]]:
    """
    Metni AI ile tematik kavram kodlarına dönüştürür.
    Tüm ağ matrisleri yalnızca bu çıktı üzerinden hesaplanmalıdır.
    """
    text = normalize_text(text)
    source_sentences = sentences_from_text(text)
    if not source_sentences:
        raise ValueError("Metinde cümle bulunamadı.")

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY tanımlı değil. .env dosyası oluşturun veya ortam değişkeni ayarlayın."
        )

    client = OpenAI(api_key=key, base_url=base_url or os.environ.get("OPENAI_BASE_URL"))
    chosen_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=chosen_model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(text=text[:120000])},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    concepts = _parse_concepts_json(raw)
    concepts = _align_sentence_count(concepts, source_sentences)
    # Boş cümleleri atma — cümle hizası matrisler için korunur; analizde boş satır sorun yok
    concepts = [filter_concept_list(c) for c in concepts]

    non_empty = [c for c in concepts if c]
    if not non_empty:
        raise ValueError("AI hiç geçerli kavram çıkaramadı. Metni kontrol edin.")

    flat = sorted({w for sent in concepts for w in sent})
    return concepts, flat


def concepts_preview(sentences: list[list[str]], limit: int = 40) -> list[dict[str, Any]]:
    from collections import Counter

    counts = Counter(w for s in sentences for w in s)
    top = counts.most_common(limit)
    return [{"concept": k, "count": v} for k, v in top]
