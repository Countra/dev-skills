"""跨中英文检索的一致文本归一化与特征提取。"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable


LATIN_TOKEN = re.compile(r"[a-z0-9]+")
CJK_SEQUENCE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    characters = []
    for character in normalized:
        category = unicodedata.category(character)
        if character.isalnum() or CJK_SEQUENCE.fullmatch(character):
            characters.append(character)
        elif category.startswith(("P", "S", "Z")) or character.isspace():
            characters.append(" ")
        else:
            characters.append(character)
    return " ".join("".join(characters).split())


def latin_tokens(value: str) -> set[str]:
    return set(LATIN_TOKEN.findall(normalize_text(value)))


def cjk_ngrams(value: str) -> set[str]:
    grams: set[str] = set()
    for sequence in CJK_SEQUENCE.findall(normalize_text(value)):
        if len(sequence) == 1:
            grams.add(sequence)
        for size in (2, 3):
            grams.update(sequence[index : index + size] for index in range(max(0, len(sequence) - size + 1)))
    return grams


def search_terms(value: str, maximum: int = 64) -> list[str]:
    terms = sorted(latin_tokens(value) | cjk_ngrams(value), key=lambda item: (-len(item), item))
    return terms[:maximum]


def all_ngrams(values: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        result.update(cjk_ngrams(value))
        result.update(latin_tokens(value))
    return result
