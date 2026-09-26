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

# Классификатор отраслей: ключ — industry value, значение — список ключевых слов.
# Слова сортированы по приоритету: чем выше в списке, тем сильнее сигнал.
INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "industrial_ai": [
        "industrial ai", "industrial ai", "промышленный ии", "промышленный искусственный интеллект",
        "manufacturing ai", "manufacturing quality", "factory automation", "factory automation",
        "industrial robot", "industrial robot", "production line", "production line",
        "industrial inspection", "industrial inspection", "process optimization",
        "industrial agent", "industrial agent", "ot agent", "ot agent",
        "plc", "scada", "mes", "erp", "digital twin", "digital twin",
        "cad-native", "generative design", "engineering intelligence",
        "autonomous welding", "autonomous welding", "adaptive welding",
        "vision foundation", "quality control", "defect detection",
        "robotics foundation model", "robotics foundation model",
        "vla model", "supply chain agent", "supply chain agent",
        "thermal management", "data center cooling", "data center cooling",
        "thermal ai", "proactive cooling", "virtual power plant", "vpp",
        "bess optimization", "virtual power plant", "vpp",
        "grid optimization", "grid optimization", "energy trading",
    ],
    "robotics": [
        "robot", "robot", "robotics", "робот", "робототехник", "робототехника",
        "quadruped", "quadruped", "humanoid", "humanoid", "dexterous hand",
        "dexterous hand", "robotic hand", "robotic hand", "grippers",
        "swarm robot", "swarm robot", "swarm robotics", "swarm robotics",
        "field robot", "field robot", "agricultural robot", "agricultural robot",
        "inspection robot", "inspection robot", "mobile robot", "mobile robot",
        "robot app store", "robot app store", "robot skill marketplace",
        "teleoperation", "teleoperation", "data-as-a-service", "data-as-a-service",
        "embodied ai", "embodied ai", "robot learning", "robot learning",
        "manipulator", "manipulator", "actuator", "actuator",
        "neuromorphic", "neuromorphic", "brain-inspired", "brain-inspired",
    ],
    "infrastructure": [
        "infrastructure", "инфраструктур", "инфраструктур",
        "data center", "data center", "ai fabric", "ai fabric",
        "optical switch", "optical switch", "o cs", "o cs",
        "wafer scale", "wafer scale", "wafer-scale", "wafer-scale",
        "kv cache", "kv cache", "kv offload", "kv offload",
        "icmsp", "nixl", "dynamo",
        "sovereign cloud", "sovereign cloud", "air-gapped", "air-gapped",
        "smr", "small modular reactor", "small modular reactor", "nuclear",
        "hbm", "high bandwidth memory", "high bandwidth memory",
        "compute cluster", "compute cluster", "ai cluster", "ai cluster",
        "interconnect", "interconnect", "infiniband", "infiniband",
        "optical interconnect", "optical interconnect",
        "space computing", "space computing", "orbital", "orbital",
        "edge data center", "edge data center",
    ],
    "fintech": [
        "fintech", "финтех", "финтех", "banking", "banking", "core banking",
        "core banking", "lending", "lending", "credit scoring", "credit scoring",
        "onchain credit", "onchain credit", "deFi", "deFi", "defi",
        "debt collection", "debt collection", "voice agent", "voice agent",
        "payment", "payment", "remittance", "remittance",
        "kyb", "kyb", "kyc", "kyc", "identity verification",
        "banking os", "banking os", "banking infrastructure",
        "sovereign ai", "sovereign ai",
    ],
    "ai_security": [
        "security", "безопаснос", "безопаснос", "ai security", "ai security",
        "prompt injection", "prompt injection", "red teaming", "red teaming",
        "mcp security", "mcp security", "tool poisoning", "tool poisoning",
        "llm firewall", "llm firewall", "ai governance", "ai governance",
        "ai compliance", "ai compliance", "eu ai act", "eu ai act",
        "privacy enhancing", "privacy enhancing", "differential privacy",
        "synthetic data", "synthetic data", "confidential inference",
        "confidential inference", "tee", "trusted execution environment",
        "trusted execution environment", "remote attestation",
        "watermarking", "watermarking", "deepfake detection", "deepfake detection",
        "identity verification", "identity verification", "liveness",
        "agent identity", "agent identity", "agent access", "agent access",
        "self-healing", "self-healing", "injection defense",
    ],
    "edge": [
        "edge", "edge", "edge ai", "edge ai", "edge computing", "edge computing",
        "on-device", "on-device", "on-device intelligence", "on-device intelligence",
        "tinyml", "tinyml", "npu", "npu", "neupro", "neupro",
        "jetson", "jetson", "nrf54", "nrf54", "axon", "axon",
        "federated learning", "federated learning", "federated learning",
        "orbital", "orbital", "satellite", "satellite",
        "iot", "iot", "sensor fusion", "sensor fusion",
        "event-based vision", "event-based vision", "event camera",
        "event camera", "neuromorphic vision", "neuromorphic vision",
        "model compression", "model compression", "model compression",
        "edge inference", "edge inference", "edge inference",
        "edge llm", "edge llm", "edge llm",
        "edge-железе", "edge-железе", "edge-железе",
    ],
    "semiconductor": [
        "semiconductor", "полупроводник", "полупроводник", "chip", "chip",
        "npu", "npu", "npu", "npu", "accelerator", "accelerator",
        "xpu", "xpu", "xpu", "xpu", "vla chip", "vla chip",
        "hyperaccel", "hyperaccel", "brainchip", "brainchip", "hailo", "hailo",
        "ceres", "ceres", "cerebras", "cerebras", "cs-4", "cs-4",
        "wafer scale", "wafer scale", "3d stack", "3d stack",
        "sram", "sr", "sr", "dr", "dr",
        "compilation", "compilation", "compiler", "compiler",
        "mojo", "mojo", "modular", "modular", "luminal", "luminal",
        "brium", "brium", "yasp", "yasp",
    ],
    "energy": [
        "energy", "энергетик", "энергетик", "nuclear", "nuclear", "smr",
        "smr", "small modular reactor", "small modular reactor",
        "fusion", "fusion", "battery", "battery", "battery",
        "bess", "bess", "virtual power plant", "virtual power plant",
        "vpp", "vpp", "grid optimization", "grid optimization",
        "geothermal", "geothermal", "solar", "solar",
        "cooling", "cooling", "data center cooling", "data center cooling",
        "pue", "pue", "liquid cooling", "liquid cooling",
        "mining", "mining", "mineral exploration", "mineral exploration",
        "earth ai", "earth ai", "geologic", "geologic",
        "climate tech", "climate tech", "sustainability", "sustainability",
    ],
    "health": [
        "health", "здравоохранен", "здравоохранен", "biotech", "biotech",
        "biomedical", "biomedical", "medical", "medical",
        "drug discovery", "drug discovery", "genomics", "genomics",
        "proteomics", "proteomics", "synthetic biology", "synthetic biology",
        "clinical trial", "clinical trial", "diagnostics", "diagnostics",
        "medical device", "medical device", "healthcare ai", "healthcare ai",
    ],
}


def classify_industry(title: str, description: str) -> str:
    """Определяет отрасль кандидата по ключевым словам в названии и описании."""
    text = (title + " " + description).casefold()
    scores: dict[str, int] = {}
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > 0:
            scores[industry] = count
    if not scores:
        return TechnologyCandidate.Industry.OTHER.value
    return max(scores, key=scores.get)


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
        industry = classify_industry(observation["title"], observation["description"])
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
            industry=industry,
        )
        candidate.source_documents.set(documents)
        created_count += 1
        weak_count += int(candidate.is_weak_signal)
        high_confidence_count += int(candidate.is_high_confidence and candidate.is_weak_signal)
    return created_count, weak_count, high_confidence_count, errors
