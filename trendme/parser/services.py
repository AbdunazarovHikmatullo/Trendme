"""Клиенты открытых источников и общая нормализация документов."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


USER_AGENT = "TrendMe/1.0 (research project)"
SOURCE_QUERY_ALIASES = {
    "квантов": ("quantum",),
    "сенсор": ("sensor",),
    "финтех": ("fintech",),
    "кибербезопас": ("cybersecurity",),
}


def _request(url: str, accept: str, timeout: int = 20) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    values: list[tuple[int, str]] = []
    for word, positions in index.items():
        if isinstance(word, str) and isinstance(positions, list):
            values.extend((position, word) for position in positions if isinstance(position, int))
    return " ".join(word for _, word in sorted(values))


def _arxiv_query(query: str) -> str:
    """arXiv преимущественно индексирует англоязычные метаданные."""
    terms: list[str] = []
    normalized = query.casefold()
    for russian_stem, aliases in SOURCE_QUERY_ALIASES.items():
        if russian_stem in normalized:
            terms.extend(aliases)
    if not terms:
        terms = [term for term in re.findall(r"[a-z0-9-]+", normalized) if len(term) >= 3]
    return " AND ".join(f"all:{term}" for term in dict.fromkeys(terms)) or f"all:{query}"


def openalex(query: str, limit: int = 30) -> list[dict[str, Any]]:
    params = urlencode({"search": query, "per-page": limit})
    payload = json.loads(_request(f"https://api.openalex.org/works?{params}", "application/json").decode("utf-8"))
    documents = []
    for item in payload.get("results", []):
        title = str(item.get("display_name") or "").strip()
        identifier = str(item.get("doi") or item.get("id") or "").strip()
        if not title or not identifier:
            continue
        location = item.get("primary_location") or {}
        documents.append({
            "provider": "openalex", "external_id": identifier, "title": title,
            "abstract": _abstract(item.get("abstract_inverted_index")),
            "url": str(item.get("doi") or location.get("landing_page_url") or item["id"]),
            "published_date": _parse_date(item.get("publication_date")),
            "source_name": "OpenAlex", "source_type": "academic",
            "language": str(item.get("language") or ""), "trust": 0.95, "raw_payload": item,
        })
    return documents


def arxiv(query: str, limit: int = 30) -> list[dict[str, Any]]:
    params = urlencode({"search_query": _arxiv_query(query), "start": 0, "max_results": limit})
    root = ElementTree.fromstring(_request(f"https://export.arxiv.org/api/query?{params}", "application/atom+xml").decode("utf-8"))
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    documents = []
    for entry in root.findall("atom:entry", namespace):
        identifier = (entry.findtext("atom:id", default="", namespaces=namespace) or "").strip()
        title = " ".join((entry.findtext("atom:title", default="", namespaces=namespace) or "").split())
        if not title or not identifier:
            continue
        documents.append({
            "provider": "arxiv", "external_id": identifier, "title": title,
            "abstract": " ".join((entry.findtext("atom:summary", default="", namespaces=namespace) or "").split()),
            "url": identifier,
            "published_date": _parse_date(entry.findtext("atom:published", default="", namespaces=namespace)),
            "source_name": "arXiv", "source_type": "preprint", "language": "en", "trust": 0.85,
            "raw_payload": {"id": identifier},
        })
    return documents
