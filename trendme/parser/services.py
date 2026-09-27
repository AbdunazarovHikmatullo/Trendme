"""Клиенты открытых источников и общая нормализация документов."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


USER_AGENT = "TrendMe/1.0 (hackathon research project)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SOURCE_QUERY_ALIASES = {
    "квантов": ("quantum",),
    "сенсор": ("sensor", "sensing"),
    "финтех": ("fintech", "financial"),
    "кибербезопас": ("cybersecurity", "security"),
    "робот": ("robot", "robotics"),
    "полупровод": ("semiconductor",),
    "энерг": ("energy",),
    "здравоохран": ("health", "biotech"),
    "медицин": ("medical", "biomedical"),
    "инфраструктур": ("infrastructure",),
    "безопаснос": ("security", "cybersecurity"),
}


def _request(url: str, accept: str, timeout: int = 20, headers: dict[str, str] | None = None) -> bytes:
    merged = {"User-Agent": USER_AGENT, "Accept": accept}
    if headers:
        merged.update(headers)
    request = Request(url, headers=merged)
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _parse_json(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> Any:
    return json.loads(_request(url, "application/json", timeout=timeout, headers=headers).decode("utf-8"))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{4}", text):
        return date(int(text), 1, 1)
    if re.fullmatch(r"\d{8}", text):
        try:
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        except ValueError:
            return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _strip_markup(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = cleaned.replace("&hellip;", "...").replace("&amp;", "&").replace("&nbsp;", " ")
    return " ".join(cleaned.split())


def english_search_query(query: str) -> str:
    """Переводит русские стебли в английские термины для англоязычных API."""
    normalized = query.casefold()
    terms: list[str] = []
    for russian_stem, aliases in SOURCE_QUERY_ALIASES.items():
        if russian_stem in normalized:
            terms.append(aliases[0])
    if terms:
        return " ".join(dict.fromkeys(terms))
    latin = [term for term in re.findall(r"[a-z0-9-]+", normalized) if len(term) >= 3]
    return " ".join(dict.fromkeys(latin)) or query.strip()


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
            terms.append(aliases[0])
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
        categories = _extract_openalex_categories(item)
        documents.append({
            "provider": "openalex", "external_id": identifier, "title": title,
            "abstract": _abstract(item.get("abstract_inverted_index")),
            "url": str(item.get("doi") or location.get("landing_page_url") or item["id"]),
            "published_date": _parse_date(item.get("publication_date")),
            "source_name": "OpenAlex", "source_type": "academic",
            "language": str(item.get("language") or ""), "trust": 0.95,
            "raw_payload": item,
            "categories": categories,
        })
    return documents


def _extract_openalex_categories(item: dict) -> list[str]:
    """Извлекает категории из OpenAlex: primary_topic → subfield → field."""
    cats: list[str] = []
    pt = item.get("primary_topic") or {}
    if pt:
        sub = pt.get("subfield") or {}
        if isinstance(sub, dict):
            cats.append(sub.get("id", "").replace("subfield.", "subfield-"))
            cats.append(sub.get("display_name", ""))
        field = pt.get("field") or {}
        if isinstance(field, dict):
            cats.append(field.get("id", "").replace("field.", "field-"))
            cats.append(field.get("display_name", ""))
    for topic in (item.get("topics") or [])[:3]:
        if isinstance(topic, dict):
            cats.append(topic.get("id", "").replace("topic.", "topic-"))
    return [c for c in cats if c]


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
        categories = _extract_arxiv_categories(entry, namespace)
        documents.append({
            "provider": "arxiv", "external_id": identifier, "title": title,
            "abstract": " ".join((entry.findtext("atom:summary", default="", namespaces=namespace) or "").split()),
            "url": identifier,
            "published_date": _parse_date(entry.findtext("atom:published", default="", namespaces=namespace)),
            "source_name": "arXiv", "source_type": "preprint", "language": "en", "trust": 0.85,
            "raw_payload": {"id": identifier},
            "categories": categories,
        })
    return documents


def _extract_arxiv_categories(entry: Any, namespace: dict) -> list[str]:
    """Извлекает arXiv категории из Atom XML."""
    cats: list[str] = []
    for cat in entry.findall("atom:category", namespace):
        term = cat.get("term", "")
        if term:
            cats.append(term)
    return cats


def build_google_patents_url(query: str, limit: int = 20) -> str:
    """Собирает JSON-endpoint Google Patents (внутренний xhr/query, без API-ключа)."""
    inner = f"q={quote(query, safe='')}&num={min(max(limit, 1), 100)}&page=0&sort=new"
    return f"https://patents.google.com/xhr/query?url={quote(inner, safe='')}&exp="


def google_patents(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Патенты: Google Patents JSON, при блоке — Europe PMC (SRC:PAT)."""
    english = english_search_query(query)
    try:
        return _google_patents_xhr(english, limit)
    except (HTTPError, TimeoutError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return _europepmc_patents(english, limit)


def _google_patents_xhr(query: str, limit: int) -> list[dict[str, Any]]:
    payload = _parse_json(
        build_google_patents_url(query, limit),
        timeout=25,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://patents.google.com/",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    clusters = payload.get("results", {}).get("cluster") or []
    rows = clusters[0].get("result") or [] if clusters else []
    documents: list[dict[str, Any]] = []
    for row in rows[:limit]:
        patent = row.get("patent") or {}
        number = str(patent.get("publication_number") or "").strip()
        title = _strip_markup(str(patent.get("title") or ""))
        if not number or not title:
            continue
        url = f"https://patents.google.com/patent/{number}"
        documents.append({
            "provider": "google_patents",
            "external_id": number,
            "title": title,
            "abstract": _strip_markup(str(patent.get("snippet") or "")),
            "url": url,
            "published_date": _parse_date(patent.get("publication_date") or patent.get("filing_date")),
            "source_name": "Google Patents",
            "source_type": "patent",
            "language": str(patent.get("language") or "en")[:16],
            "trust": 0.95,
            "raw_payload": {"publication_number": number, "id": row.get("id")},
            "categories": _extract_ipc_codes_from_search(str(patent.get("snippet") or "")),
        })
    return documents


def _europepmc_patents(query: str, limit: int) -> list[dict[str, Any]]:
    """Открытый fallback по патентам, если Google Patents недоступен."""
    search = f"SRC:PAT {query}"
    payload = _parse_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
        + urlencode({"query": search, "format": "json", "pageSize": limit, "resultType": "core"}),
    )
    documents: list[dict[str, Any]] = []
    for item in (payload.get("resultList") or {}).get("result") or []:
        title = _strip_markup(str(item.get("title") or ""))
        identifier = str(item.get("id") or "").strip()
        if not title or not identifier:
            continue
        documents.append({
            "provider": "europepmc_patents",
            "external_id": identifier,
            "title": title,
            "abstract": _strip_markup(str(item.get("abstractText") or "")),
            "url": f"https://europepmc.org/article/PAT/{identifier}",
            "published_date": _parse_date(item.get("firstPublicationDate") or item.get("pubYear")),
            "source_name": "Europe PMC Patents",
            "source_type": "patent",
            "language": str(item.get("language") or "en")[:16],
            "trust": 0.9,
            "raw_payload": {"id": identifier, "source": item.get("source")},
            "categories": [],
        })
    return documents


def wikipedia(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Статьи Wikipedia: английская вики по EN-запросу и русская по исходному."""
    documents = _wikipedia_lang("en", english_search_query(query), limit)
    russian_query = query.strip()
    if re.search(r"[а-яё]", russian_query.casefold()):
        documents.extend(_wikipedia_lang("ru", russian_query, limit))
    return documents


def _wikipedia_lang(lang: str, query: str, limit: int) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    search = _parse_json(
        f"https://{lang}.wikipedia.org/w/api.php?"
        + urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": limit, "format": "json",
        }),
        headers={"User-Agent": USER_AGENT},
    )
    hits = (search.get("query") or {}).get("search") or []
    titles = [str(hit.get("title") or "").strip() for hit in hits if hit.get("title")]
    if not titles:
        return []
    details = _parse_json(
        f"https://{lang}.wikipedia.org/w/api.php?"
        + urlencode({
            "action": "query", "prop": "extracts|info|revisions",
            "exintro": 1, "explaintext": 1, "inprop": "url",
            "rvprop": "timestamp", "format": "json", "titles": "|".join(titles),
        }),
        headers={"User-Agent": USER_AGENT},
    )
    pages = ((details.get("query") or {}).get("pages") or {}).values()
    documents: list[dict[str, Any]] = []
    for page in pages:
        title = str(page.get("title") or "").strip()
        url = str(page.get("fullurl") or "").strip()
        if not title or not url or page.get("missing") is not None:
            continue
        revisions = page.get("revisions") or []
        timestamp = revisions[0].get("timestamp") if revisions else None
        documents.append({
            "provider": "wikipedia",
            "external_id": f"{lang}:{page.get('pageid') or title}",
            "title": title,
            "abstract": _strip_markup(str(page.get("extract") or ""))[:4000],
            "url": url,
            "published_date": _parse_date(timestamp),
            "source_name": "Wikipedia",
            "source_type": "encyclopedia",
            "language": lang,
            "trust": 0.75,
            "raw_payload": {"lang": lang, "pageid": page.get("pageid")},
            "categories": [],
        })
    return documents


def crossref(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Издательские записи Crossref (DOI) — независимый академический контур."""
    payload = _parse_json(
        "https://api.crossref.org/works?"
        + urlencode({
            "query": english_search_query(query),
            "rows": max(limit, 20),
            "filter": "type:journal-article,type:proceedings-article,type:posted-content",
        }),
        headers={"User-Agent": USER_AGENT},
    )
    documents: list[dict[str, Any]] = []
    for item in ((payload.get("message") or {}).get("items") or []):
        titles = item.get("title") or []
        title = _strip_markup(str(titles[0] if titles else ""))
        identifier = str(item.get("DOI") or item.get("URL") or "").strip()
        if not title or not identifier:
            continue
        published = (
            ((item.get("published") or {}).get("date-parts") or [[]])[0]
            or ((item.get("issued") or {}).get("date-parts") or [[]])[0]
            or ((item.get("published-print") or {}).get("date-parts") or [[]])[0]
        )
        published_date = None
        if published:
            year = int(published[0])
            month = int(published[1]) if len(published) > 1 else 1
            day = int(published[2]) if len(published) > 2 else 1
            published_date = _parse_date(f"{year:04d}-{month:02d}-{day:02d}")
        documents.append({
            "provider": "crossref",
            "external_id": identifier,
            "title": title,
            "abstract": _strip_markup(str(item.get("abstract") or "")),
            "url": str(item.get("URL") or f"https://doi.org/{identifier}"),
            "published_date": published_date,
            "source_name": "Crossref",
            "source_type": "academic",
            "language": str(item.get("language") or "en")[:16],
            "trust": 0.9,
            "raw_payload": {"DOI": identifier, "type": item.get("type")},
            "categories": [str(item.get("type") or "")],
        })
        if len(documents) >= limit:
            break
    return documents


def europepmc(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """PubMed / Europe PMC — медицина, биотех и смежные публикации."""
    payload = _parse_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
        + urlencode({
            "query": f"({english_search_query(query)}) NOT SRC:PAT",
            "format": "json",
            "pageSize": limit,
            "resultType": "core",
        }),
    )
    documents: list[dict[str, Any]] = []
    for item in (payload.get("resultList") or {}).get("result") or []:
        title = _strip_markup(str(item.get("title") or ""))
        identifier = str(item.get("id") or item.get("pmid") or item.get("doi") or "").strip()
        if not title or not identifier:
            continue
        source = str(item.get("source") or "MED")
        doi = str(item.get("doi") or "").strip()
        url = f"https://doi.org/{doi}" if doi else f"https://europepmc.org/article/{source}/{identifier}"
        documents.append({
            "provider": "europepmc",
            "external_id": identifier,
            "title": title,
            "abstract": _strip_markup(str(item.get("abstractText") or "")),
            "url": url,
            "published_date": _parse_date(item.get("firstPublicationDate") or item.get("pubYear")),
            "source_name": "Europe PMC",
            "source_type": "academic",
            "language": str(item.get("language") or "en")[:16],
            "trust": 0.9,
            "raw_payload": {"id": identifier, "source": source},
            "categories": [str(item.get("pubType") or "")],
        })
    return documents


def _extract_text_from_html(html: str, tag: str, cls: str) -> str:
    """Извлекает текст из HTML по тегу и классу."""
    pattern = rf'<{tag}[^>]*class="{cls}"[^>]*>(.*?)</{tag}>'
    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if match:
        text = re.sub(r"<[^>]+>", " ", match.group(1))
        return text.strip()
    return ""


def _extract_href_from_html(html: str, tag: str, cls: str) -> str:
    """Извлекает href из HTML по тегу и классу."""
    pattern = rf'<{tag}[^>]*class="{cls}"[^>]*href="([^"]+)"'
    match = re.search(pattern, html, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _extract_ipc_codes_from_search(html: str) -> list[str]:
    """Извлекает IPC-коды из строки результатов поиска Google Patents."""
    codes: list[str] = []
    ipc_pattern = r"\b([A-Z]\d{2}[A-Z]?\s*\d{1,2}/\d{2})\b"
    for match in re.finditer(ipc_pattern, html):
        code = match.group(1).replace(" ", "").replace("/", "-")
        if code and code not in codes:
            codes.append(code)
    cpc_pattern = r"\b([A-Z]\d{2}[A-Z]?\s*\d{4}\.\d{2})\b"
    for match in re.finditer(cpc_pattern, html):
        code = match.group(1).replace(" ", "").replace(".", "-")
        if code and code not in codes:
            codes.append(code)
    return codes[:10]


def _extract_date_from_search(html: str) -> str | None:
    """Извлекает дату публикации из строки результатов поиска."""
    patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"Published:\s*(\d{4})\s+(\w+)\s+(\d{1,2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
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


def _extract_patent_id(url: str) -> str:
    """Извлекает номер патента из URL Google Patents."""
    match = re.search(r"(\d{8,})", url)
    if match:
        return match.group(1)
    return ""


def _extract_patent_details(url: str) -> tuple[str, str | None, list[str]]:
    """Извлекает abstract, publication date и IPC-коды со страницы патента."""
    abstract = ""
    pub_date: str | None = None
    ipc_codes: list[str] = []
    try:
        html = _request(url, "text/html", timeout=15).decode("utf-8")
        abstract = _parse_html_section(html, "abstract")
        pub_date = _parse_html_date(html)
        ipc_codes = _extract_ipc_codes(html)
    except Exception:
        pass
    return abstract, pub_date, ipc_codes


def _extract_ipc_codes(html: str) -> list[str]:
    """Извлекает IPC/CPC коды из HTML страницы Google Patents."""
    codes: list[str] = []
    ipc_pattern = r"\b([A-Z]\d{2}[A-Z]?\s*\d{1,2}/\d{2})\b"
    for match in re.finditer(ipc_pattern, html):
        code = match.group(1).replace(" ", "").replace("/", "-")
        if code and code not in codes:
            codes.append(code)
    cpc_pattern = r"\b([A-Z]\d{2}[A-Z]?\s*\d{4}\.\d{2})\b"
    for match in re.finditer(cpc_pattern, html):
        code = match.group(1).replace(" ", "").replace(".", "-")
        if code and code not in codes:
            codes.append(code)
    return codes[:10]


def _parse_html_section(html: str, section_id: str) -> str:
    """Извлекает текст секции по ID из HTML (abstract, description и т.д.)."""
    patterns = [
        rf'<div[^>]*id="{section_id}[^"]*"[^>]*>(.*?)</div>',
        rf'<section[^>]*id="{section_id}[^"]*"[^>]*>(.*?)</section>',
        rf'<div[^>]*class="{section_id}[^"]*"[^>]*>(.*?)</div>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.DOTALL | re.IGNORECASE)
        if match:
            text = re.sub(r"<[^>]+>", " ", match.group(1))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                return text
    return ""


def _parse_html_date(html: str) -> str | None:
    """Извлекает дату публикации из метаданных или секции патента."""
    patterns = [
        r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})"',
        r'<meta[^>]*name="date"[^>]*content="(\d{4}-\d{2}-\d{2})"',
        r'<meta[^>]*property="article:published_time"[^>]*content="(\d{4}-\d{2}-\d{2})"',
        r"Published:\s*(\d{4})\s+(\w+)\s+(\d{1,2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
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
