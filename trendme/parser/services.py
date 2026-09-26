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


def google_patents(query: str, limit: int = 30) -> list[dict[str, Any]]:
    """Получает патенты через Google Patents RSS + извлекает аннотации со страниц."""
    params = urlencode({"q": query, "max": limit})
    rss_url = f"https://www.google.com/patents/rss?q={params}"
    try:
        raw = _request(rss_url, "application/atom+xml")
    except Exception:
        return []

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    root = ElementTree.fromstring(raw.decode("utf-8"))
    entries = root.findall("atom:entry", namespace)

    documents: list[dict[str, Any]] = []
    for entry in entries:
        link = (entry.findtext("atom:link", default="", namespaces=namespace) or "").strip()
        title = " ".join((entry.findtext("atom:title", default="", namespaces=namespace) or "").split())
        if not title or not link:
            continue

        abstract, pub_date = _extract_patent_details(link)
        external_id = _extract_patent_id(link)

        documents.append({
            "provider": "google_patents",
            "external_id": external_id or link,
            "title": title,
            "abstract": " ".join(abstract.split()) if abstract else "",
            "url": link,
            "published_date": _parse_date(pub_date) or pub_date,
            "source_name": "Google Patents",
            "source_type": "patent",
            "language": "en",
            "trust": 0.95,
            "raw_payload": {"link": link, "title": title},
        })
    return documents


def _extract_patent_id(url: str) -> str:
    """Извлекает номер патента из URL Google Patents."""
    import re as _re
    match = _re.search(r"(\d{8,})", url)
    if match:
        return match.group(1)
    return ""


def _extract_patent_details(url: str) -> tuple[str, str | None]:
    """Извлекает abstract и publication date со страницы патента."""
    abstract = ""
    pub_date: str | None = None
    try:
        html = _request(url, "text/html", timeout=15).decode("utf-8")
        abstract = _parse_html_section(html, "abstract")
        pub_date = _parse_html_date(html)
    except Exception:
        pass
    return abstract, pub_date


def _parse_html_section(html: str, section_id: str) -> str:
    """Извлекает текст секции по ID из HTML (abstract, description и т.д.)."""
    import re as _re
    patterns = [
        rf'<div[^>]*id="{section_id}[^"]*"[^>]*>(.*?)</div>',
        rf'<section[^>]*id="{section_id}[^"]*"[^>]*>(.*?)</section>',
        rf'<div[^>]*class="{section_id}[^"]*"[^>]*>(.*?)</div>',
    ]
    for pattern in patterns:
        match = _re.search(pattern, html, flags=_re.DOTALL | _re.IGNORECASE)
        if match:
            text = _re.sub(r"<[^>]+>", " ", match.group(1))
            text = _re.sub(r"\s+", " ", text).strip()
            if text:
                return text
    return ""


def _parse_html_date(html: str) -> str | None:
    """Извлекает дату публикации из метаданных или секции патента."""
    import re as _re
    patterns = [
        r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})"',
        r'<meta[^>]*name="date"[^>]*content="(\d{4}-\d{2}-\d{2})"',
        r'<meta[^>]*property="article:published_time"[^>]*content="(\d{4}-\d{2}-\d{2})"',
        r"Published:\s*(\d{4})\s+(\w+)\s+(\d{1,2})",
    ]
    for pattern in patterns:
        match = _re.search(pattern, html, flags=_re.IGNORECASE)
        if match:
            date_str = match.group(1)
            if len(date_str) == 4:
                months = {
                    "january": "01", "february": "02", "march": "03", "april": "04",
                    "may": "05", "june": "06", "july": "07", "august": "08",
                    "september": "09", "october": "10", "november": "11", "december": "12",
                }
                month_num = months.get(match.group(2).lower())
                if month_num:
                    day = match.group(3).zfill(2)
                    return f"{date_str}-{month_num}-{day}"
            return date_str
    return None
