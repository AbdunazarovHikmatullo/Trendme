"""Предобработка текста: очистка и нормализация для поиска маркеров."""

import re

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_NON_ALPHA_RE = re.compile(r"[^a-zа-яё0-9\s-]+")
_WS_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = _URL_RE.sub(" ", text)
    text = text.replace("\n", " ").replace("\t", " ")
    return text


def normalize_for_markers(text: str) -> str:
    text = clean_text(text).lower()
    text = _NON_ALPHA_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text
