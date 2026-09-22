"""Агрегация документов в кандидатов и обращение к изолированному ML-сервису."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from urllib.request import Request, urlopen

from parser.models import SourceDocument

from .models import SearchRun, TechnologyCandidate


ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://ml:8001").rstrip("/")
TITLE_RE = re.compile(r"[^\w\s]", re.UNICODE)
TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
MAX_CANDIDATES = 15
MAX_AGE_YEARS = 5
STOP_WORDS = {
    "about", "among", "analysis", "approach", "based", "between", "design", "effects", "from", "into", "methods",
    "model", "models", "novel", "research", "results", "study", "system", "systems", "technology", "using", "with",
    "данные", "исследование", "метод", "методы", "модель", "научные", "новые", "основе", "подход", "применение",
    "прототип", "prototype", "early", "разработка", "системы", "технологии", "устройство",
}

# Минимальный словарь нужен, чтобы русскоязычный запрос находил англоязычные
# публикации. Расширяем его постепенно на основании журнала поисков.
QUERY_ALIASES = {
    "квантов": ("quantum",),
    "сенсор": ("sensor", "sensing"),
    "финтех": ("fintech", "financial technology"),
    "кибербезопас": ("cybersecurity", "cyber security"),
}


@dataclass
class CandidateGroup:
    documents: list[SourceDocument]
    label: str | None = None

    @property
    def title(self) -> str:
        return self.label or self.documents[0].title


def _key(title: str) -> str:
    return " ".join(TITLE_RE.sub(" ", title.casefold()).split())


def _tokens(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.casefold()) if len(token) >= 4 and token not in STOP_WORDS}


def _query_terms(query: str) -> set[str]:
    terms = _tokens(query)
    for stem, aliases in QUERY_ALIASES.items():
        if any(token.startswith(stem) for token in terms):
            terms.update(aliases)
    return terms


def _is_relevant(document: SourceDocument, query_terms: set[str]) -> bool:
    """Отсекает публикации, попавшие в полнотекстовый поиск случайно.

    Совпадение в названии сильнее совпадения в абстракте: так документ об UFO,
    случайно упоминающий квантовые сенсоры, не становится технологией-кандидатом.
    """
    title_tokens = _tokens(document.title)
    text_tokens = title_tokens | _tokens(document.abstract[:2000])
    title_hits = sum(any(token.startswith(term) or term.startswith(token) for token in title_tokens) for term in query_terms)
    text_hits = sum(any(token.startswith(term) or term.startswith(token) for token in text_tokens) for term in query_terms)
    required_hits = 1 if len(query_terms) == 1 else 2
    return title_hits >= 1 and text_hits >= required_hits


def _is_recent(document: SourceDocument) -> bool:
    if not document.published_date:
        return False
    return date.today().year - document.published_date.year <= MAX_AGE_YEARS


def _technical_profile(document: SourceDocument, query_terms: set[str]) -> set[str]:
    """Технические понятия для лёгкой тематической кластеризации без внешней модели."""
    text = f"{document.title} {document.abstract[:1800]}"
    query_roots = {term[:6] for term in query_terms}
    return {
        token for token in _tokens(text)
        if token[:6] not in query_roots and len(token) >= 5
    }


def _similar(left: CandidateGroup, right: SourceDocument, query_terms: set[str]) -> bool:
    """Объединяет статьи вокруг общего технического понятия, а не только одинакового заголовка."""
    query_roots = {term[:6] for term in query_terms}
    left_tokens = {token for token in _tokens(left.title) if token[:6] not in query_roots}
    right_tokens = {token for token in _tokens(right.title) if token[:6] not in query_roots}
    if left_tokens and right_tokens and len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= 0.55:
        return True
    left_profile = set().union(*(_technical_profile(document, query_terms) for document in left.documents))
    right_profile = _technical_profile(right, query_terms)
    # Два специфичных общих понятия (например, "atomic" + "magnetometer")
    # являются более надёжным признаком одной технологии, чем общий запрос.
    return len(left_profile & right_profile) >= 2


def _group(documents: list[SourceDocument], query_terms: set[str], query: str) -> list[CandidateGroup]:
    groups: list[CandidateGroup] = []
    for document in documents:
        exact = next((group for group in groups if _key(group.title) == _key(document.title)), None)
        similar = exact or next((group for group in groups if _similar(group, document, query_terms)), None)
        if similar:
            similar.documents.append(document)
        else:
            groups.append(CandidateGroup(documents=[document]))

    # Если литература релевантна, но её названия слишком разнородны для узкого
    # поднаправления, формируем один явно названный тематический кандидат. Это
    # лучше, чем ошибочно считать каждую статью отдельным трендом.
    confirmed = [group for group in groups if _has_sufficient_evidence(group.documents)]
    if not confirmed and len(documents) >= 2:
        return [CandidateGroup(documents=documents, label=query.strip().capitalize())]
    return groups


def _has_sufficient_evidence(documents: list[SourceDocument]) -> bool:
    """Один блог/препринт не является достаточным основанием для итоговой выдачи."""
    if any(document.source_type == "patent" for document in documents):
        return True
    # Провайдер (например OpenAlex) — агрегатор, а не первоисточник. Независимость
    # подтверждают две разные публикации/URL либо патент.
    return len({document.url for document in documents}) >= 2


def _observation(documents: list[SourceDocument], title: str | None = None) -> dict:
    first_date = min((doc.published_date for doc in documents if doc.published_date), default=None)
    source_types = [doc.source_type for doc in documents]
    return {
        "title": title or documents[0].title,
        "description": " ".join(doc.abstract for doc in documents if doc.abstract)[:8000],
        "source_type": "academic" if "academic" in source_types else source_types[0],
        "published_date": first_date.isoformat() if first_date else None,
        "mentions": len(documents),
        "has_patent": "patent" in source_types,
        "source_trust": round(sum(doc.trust for doc in documents) / len(documents), 3),
    }


def _predict(observation: dict) -> dict:
    payload = json.dumps({"observations": [observation], "top_n": 1}).encode("utf-8")
    request = Request(
        f"{ML_SERVICE_URL}/predict", data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["predictions"][0]


def build_candidates(run: SearchRun) -> tuple[int, int, int, list[str]]:
    """Фильтрует и ранжирует не более 15 подтверждённых слабых сигналов."""
    query_terms = _query_terms(run.query)
    selected_documents = [
        document for document in run.documents.all().order_by("-published_date")
        if _is_recent(document) and _is_relevant(document, query_terms)
    ]
    grouped = [group for group in _group(selected_documents, query_terms, run.query) if _has_sufficient_evidence(group.documents)]

    run.candidates.all().delete()
    errors: list[str] = []
    created_count = weak_count = high_confidence_count = 0
    scored: list[tuple[dict, dict, list[SourceDocument]]] = []
    for group in grouped:
        documents = group.documents
        observation = _observation(documents, group.title)
        try:
            prediction = _predict(observation)
        except Exception as error:
            errors.append(f"ML: {error}")
            continue
        if prediction["weak_signal"]:
            scored.append((prediction, observation, documents))

    for prediction, observation, documents in sorted(scored, key=lambda item: item[0]["confidence"], reverse=True)[:MAX_CANDIDATES]:
        candidate = TechnologyCandidate.objects.create(
            run=run,
            title=observation["title"],
            description=observation["description"][:4000],
            potential_benefit="Требует экспертной оценки по подтверждающим источникам.",
            case_example="Исходная научная публикация или препринт из списка источников.",
            confidence=prediction["confidence"],
            is_weak_signal=prediction["weak_signal"],
            is_high_confidence=prediction["confidence"] >= 0.75,
            explanation=prediction["explanation"],
            factors=prediction["factors"],
        )
        candidate.source_documents.set(documents)
        created_count += 1
        weak_count += int(candidate.is_weak_signal)
        high_confidence_count += int(candidate.is_high_confidence and candidate.is_weak_signal)
    return created_count, weak_count, high_confidence_count, errors
