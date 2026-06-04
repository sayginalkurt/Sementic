"""Metin ön işleme: cümle bölme, tokenizasyon, Türkçe durak kelimeler."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# English stopwords (AI concept pipeline; CLI may still use Turkish list)
ENGLISH_STOPWORDS = frozenset(
    """
    a an the and or nor but if because as at by for from in into of on onto
    to with without about above across after against along amid among around
    before behind below beneath beside besides between beyond during except
    inside near off out outside over past per through throughout till toward
    towards under underneath unlike until up upon via within without
    i me my mine we us our ours you your yours he him his she her hers it its
    they them their theirs this that these those who whom whose which what
    when where why how all any both each few more most other some such no
    nor not only own same so than too very just also still even already
    then once here there now again ever never always sometimes often usually
    really quite rather perhaps maybe yes no ok okay well um uh like kind
    sort type thing things something someone somebody anyone everybody nobody
    people person human humans being beings one ones another others each other
    would could should may might must shall will can do does did done doing
    have has had having be am is are was were been being get gets got getting
    make makes made making go goes went going come comes came coming say says
    said saying think thinks thought know knows knew see sees saw want wants
    need needs use uses used using take takes took give gives gave tell tells
    feel feels felt seem seems seemed look looks looked become becomes became
    there their they're its it's
    """.split()
)

# Sık kullanılan Türkçe durak kelimeler (CLI / tokenize yolu)
TURKISH_STOPWORDS = frozenset(
    """
    acaba altı ama ancak artık aslında az biraz bile birçok biri birkaç birşey
    böyle bu buna bunda bunlar bunu bunun burada bütün çok çünkü da daha de
    dedi değil diye eğer en fakat için gibi hem hep hiç ile ise işte
    kadar ki kim kimse mi mı mu mü nasıl ne neden niçin o olan ona onlar
    onu onun oysa pek rağmen sadece sanki şey şu şuna şunu şunun tabii tam
    tüm ve veya ya yani yine yok zaten bir iki ben sen biz siz
    benim senin onun bizim sizin burada orada şimdi sonra önce
    var yok olur oluyor olmuş olacak oldu olması
  """.split()
)

WORD_PATTERN = re.compile(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]+", re.UNICODE)
SENTENCE_SPLIT = re.compile(r"[.!?…]+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in WORD_PATTERN.findall(normalize_text(text))]


def is_content_word(word: str, min_len: int = 2) -> bool:
    return len(word) >= min_len and word not in TURKISH_STOPWORDS


def sentences_from_text(text: str) -> list[str]:
    text = normalize_text(text)
    chunks = [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]
    return chunks


def tokens_by_sentence(text: str, min_len: int = 2) -> list[list[str]]:
    result: list[list[str]] = []
    for sent in sentences_from_text(text):
        tokens = [w for w in tokenize(sent) if is_content_word(w, min_len)]
        if tokens:
            result.append(tokens)
    return result


def build_vocabulary(
    token_lists: Iterable[list[str]],
    min_freq: int = 2,
) -> list[str]:
    from collections import Counter

    counts: Counter[str] = Counter()
    for tokens in token_lists:
        counts.update(tokens)
    return sorted(w for w, c in counts.items() if c >= min_freq)
