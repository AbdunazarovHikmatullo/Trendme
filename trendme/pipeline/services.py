"""Агрегация документов в кандидатов и обращение к изолированному ML-сервису."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from urllib.request import Request, urlopen

from parser.models import SourceDocument
from parser.services import SOURCE_QUERY_ALIASES, english_search_query, query_needs_translation

from .models import SearchRun, TechnologyCandidate


ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://ml:8001").rstrip("/")
TITLE_RE = re.compile(r"[^\w\s]", re.UNICODE)
TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
MAX_CANDIDATES = 15
MAX_AGE_YEARS = 5
CORE_SOURCE_TYPES = frozenset({"academic", "preprint"})
SUPPORT_SOURCE_TYPES = frozenset({"patent", "encyclopedia"})
NOISE_TITLE_RE = re.compile(
    r"\b(list of|overview of|index of|timeline of|history of|how to|special issue|"
    r"conference|workshop|symposium|editorial|in education|pedagogy|curriculum|"
    r"systematic review|a review|review and|philosophical|ontological|"
    r"fermi paradox|social interaction|comparison of humans|metaverse|"
    r"education|postgraduate|survey|helpfulness|limits of|limit of|bounds on|"
    r"a theory of|theory of|comment on|towards understanding|"
    r"the role of|revolutionizing|in clinical practice|the future of|"
    r"recent advances|progress in|state of the art|state-of-the-art|"
    r"for high energy physics|in organic synthesis|perspectives on|"
    r"in healthcare|in agriculture)\b|"
    r"\bresearch$|"
    r"^список\b|маркетплейс|учетно-контроль|1с:|\bмерч\b|"
    r"конференц|симпозиум|педагогик|образован|как измерить|телесериал|"
    r"спецвыпуск|анонс|круглый стол|философ",
    re.IGNORECASE,
)
MIN_ABSTRACT_CHARS = 80
TITLE_SIMILARITY = 0.90
SUPPORT_JACCARD = 0.35
MAX_WIKI_PER_GROUP = 1
MAX_PATENTS_PER_GROUP = 2
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv:)(\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)
ARTIFACT_RE = re.compile(
    r"\b(prototype|prototyp|device|platform|detector|fabricat|demonstrat|"
    r"we report|we present|we demonstrate|we propose|we develop|"
    r"architecture|instrument|magnetometer|accelerometer|implementation|"
    r"experimental|experiment|readout|transducer|qubit|nv-center|"
    r"nitrogen-vacancy|apparatus|setup|accelerator|processor|memristor|"
    r"electrolyte|anode|cathode|chip-scale|on-chip|"
    r"прототип|устройств|детектор|экспериментальн|демонстрац|"
    r"мы представляем|мы сообщаем)\b",
    re.IGNORECASE,
)
APPLICATION_RE = re.compile(
    r"\b(for|enabling|toward|towards|application|used to|use in|enables|"
    r"allowing|применен|позволя)\b",
    re.IGNORECASE,
)
INSTRUMENT_RE = re.compile(
    r"\b(?:using|with|via)\b.{0,48}\bquantum sensors?\b",
    re.IGNORECASE,
)
FIELD_ONLY_STEMS = frozenset({
    "искусственн", "интеллект", "нейросет", "энерг", "технолог",
})
COMMERCIAL_RE = re.compile(
    r"\b(widely used|industry standard|mass production|commercially available|"
    r"mainstream|mature market|commodity)\b",
    re.IGNORECASE,
)
MENTIONS_PER_EXTRA_HIT = 40
MAX_ML_MENTIONS = 400
OFFTOPIC_MARKERS = (
    ("blockchain", ("blockchain", "блокчейн")),
    ("routing", ("routing", "маршрутиз")),
    ("post-quantum", ("post-quantum", "postquantum", "постквант")),
    ("post quantum", ("post-quantum", "postquantum", "постквант")),
)
STOP_WORDS = {
    "about", "among", "analysis", "approach", "based", "between", "design", "effects", "from", "into", "methods",
    "model", "models", "novel", "research", "results", "study", "system", "systems", "technology", "using", "with",
    "данные", "исследование", "метод", "методы", "модель", "научные", "новые", "основе", "подход", "применение",
    "прототип", "prototype", "early", "разработка", "системы", "технологии", "устройство",
}

# Минимальный словарь нужен, чтобы русскоязычный запрос находил англоязычные
# публикации. Расширяем его постепенно на основании журнала поисков.
QUERY_ALIASES = SOURCE_QUERY_ALIASES

# Маппинг категорий источников → наши 10 отраслей
# OpenAlex topics, arXiv categories, IPC/CPC коды
SOURCE_CATEGORY_MAP: dict[str, str] = {
    # --- OpenAlex fields ---
    "field-computer science": "industrial_ai",
    "field-artificial intelligence": "industrial_ai",
    "field-engineering": "infrastructure",
    "field-electrical and electronic engineering": "semiconductor",
    "field-physics and astronomy": "semiconductor",
    "subfield-computer science": "industrial_ai",
    "subfield-artificial intelligence": "industrial_ai",
    "subfield-computer networks and communications": "infrastructure",
    "subfield-hardware and architecture": "semiconductor",
    "subfield-theory of computation": "infrastructure",
    "subfield-human-computer interaction": "edge",
    "subfield-information systems": "fintech",
    "subfield-databases": "infrastructure",
    "subfield-cryptography and security": "ai_security",
    "subfield-machine learning": "industrial_ai",
    "subfield-computer vision": "industrial_ai",
    "subfield-robotics": "robotics",
    "subfield-control and systems engineering": "infrastructure",
    "subfield-numerical analysis": "infrastructure",
    "subfield-statistics and probability": "industrial_ai",
    "subfield-economics and econometrics": "fintech",
    "subfield-finance": "fintech",
    "subfield-accounting": "fintech",
    "subfield-physics": "semiconductor",
    "subfield-materials science": "semiconductor",
    "subfield-energy": "energy",
    "subfield-biotechnology": "health",
    "subfield-medicine": "health",
    "subfield-health": "health",
    "subfield-pharmacology": "health",
    "subfield-agricultural and biological engineering": "energy",
    "subfield-mechanical engineering": "robotics",
    "subfield-chemical engineering": "energy",
    # --- arXiv categories ---
    "cs.AI": "industrial_ai",
    "cs.LG": "industrial_ai",
    "cs.RO": "robotics",
    "cs.CV": "industrial_ai",
    "cs.CR": "ai_security",
    "cs.SE": "industrial_ai",
    "cs.DB": "infrastructure",
    "cs.DC": "infrastructure",
    "cs.NE": "semiconductor",
    "cs.MA": "robotics",
    "cs.SD": "industrial_ai",
    "cs.HC": "edge",
    "cs.IR": "industrial_ai",
    "cs.DS": "infrastructure",
    "cs.PL": "infrastructure",
    "cs.AR": "semiconductor",
    "cs.ET": "infrastructure",
    "cs.OH": "industrial_ai",
    "stat.ML": "industrial_ai",
    "econ.EM": "fintech",
    "q.Bio": "health",
    "physics.comp-ph": "semiconductor",
    "physics.ins-det": "edge",
    "eess.SP": "edge",
    "eess.SY": "infrastructure",
    # --- IPC/CPC codes ---
    "G06N": "industrial_ai",
    "G06N3": "industrial_ai",
    "G06N20": "ai_security",
    "G06Q": "fintech",
    "G06Q40": "fintech",
    "H04L": "ai_security",
    "H04L9": "ai_security",
    "H04L63": "ai_security",
    "H01L": "semiconductor",
    "H01L21": "semiconductor",
    "B25J": "robotics",
    "B25J13": "robotics",
    "B25J9": "robotics",
    "B25J11": "robotics",
    "B60L": "energy",
    "B60K": "energy",
    "F24D": "energy",
    "F24F": "energy",
    "A61B": "health",
    "A61K": "health",
    "A61P": "health",
    "C12M": "health",
    "C12N": "health",
    "G01N": "health",
    "G06F": "infrastructure",
    "G06F1": "edge",
    "G06F16": "infrastructure",
    "G06F21": "ai_security",
    "G05B": "infrastructure",
    "G06T": "industrial_ai",
    "G05B23": "infrastructure",
    "H02J": "energy",
    "H02S": "energy",
    "H03M": "ai_security",
    "H04B": "infrastructure",
    "H04W": "edge",
    "H05K": "semiconductor",
    "Y02T": "energy",
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


def _categories_to_industry(categories: list[str]) -> str | None:
    """Маппинг категорий источников → наша отрасль.
    
    Возвращает industry value (например 'fintech') или None если не определилось.
    """
    for cat in categories:
        cat_lower = cat.lower().strip()
        # Прямое совпадение
        if cat_lower in SOURCE_CATEGORY_MAP:
            return SOURCE_CATEGORY_MAP[cat_lower]
        # Частичное совпадение (IPC-код начинается с префикса)
        for key, industry in SOURCE_CATEGORY_MAP.items():
            if cat_lower.startswith(key.lower()):
                return industry
    return None


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


def _title_token_list(title: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(title.casefold()) if len(token) >= 3]


def _query_terms(query: str) -> set[str]:
    terms = _tokens(query)
    for stem, aliases in QUERY_ALIASES.items():
        if stem in query.casefold() or any(token.startswith(stem) for token in terms):
            terms.update(aliases)
    return terms


def _query_concept_groups(query: str) -> list[set[str]]:
    raw = _tokens(query)
    groups: list[set[str]] = []
    for stem, aliases in QUERY_ALIASES.items():
        if stem in query.casefold() or any(token.startswith(stem) for token in raw):
            groups.append({stem, *aliases})
    if groups:
        return groups
    english_parts = [part for part in english_search_query(query).casefold().split() if len(part) >= 3]
    return [{part} for part in english_parts] or [raw]


def _hits_group(title_tokens: set[str], group: set[str]) -> bool:
    return any(
        any(token.startswith(term) or term.startswith(token) for token in title_tokens)
        for term in group
        if len(term) >= 4
    )


def _has_query_phrase(title: str, query: str) -> bool:
    parts = [part for part in english_search_query(query).casefold().split() if len(part) >= 3]
    if len(parts) < 2:
        return False
    pairs = [parts[:2]]
    if parts[1].startswith("sensor"):
        pairs.append([parts[0], "sensing"])
    tokens = _title_token_list(title)
    for first, second in pairs:
        for index, token in enumerate(tokens):
            if not (token.startswith(first) or first.startswith(token)):
                continue
            for neighbor in tokens[index + 1:index + 3]:
                if neighbor.startswith(second) or second.startswith(neighbor):
                    return True
    return False


def _is_offtopic_title(title: str, query: str) -> bool:
    haystack = f"{query} {english_search_query(query)}".casefold()
    folded = title.casefold()
    for marker, query_synonyms in OFFTOPIC_MARKERS:
        if marker in folded and not any(synonym in haystack for synonym in query_synonyms):
            return True
    return False


def _is_relevant(document: SourceDocument, query: str, _query_terms: set[str]) -> bool:
    """Допуск только если ядерные понятия запроса стоят в названии, не в случайном абстракте."""
    if _is_offtopic_title(document.title, query):
        return False
    title_tokens = _tokens(document.title)
    if _has_query_phrase(document.title, query):
        return True
    groups = _query_concept_groups(query)
    return bool(groups) and all(_hits_group(title_tokens, group) for group in groups)


def _is_noise_title(document: SourceDocument) -> bool:
    """Отсекает списки, обзоры, конференции и гуманитарный шум — это не проект."""
    return bool(NOISE_TITLE_RE.search(document.title))


def _specific_tokens(title: str, query_terms: set[str]) -> set[str]:
    query_roots = {term[:6] for term in query_terms}
    return {token for token in _tokens(title) if token[:6] not in query_roots}


def _specific_title_tokens(document: SourceDocument, query_terms: set[str]) -> set[str]:
    return _specific_tokens(document.title, query_terms)


def _is_generic_topic(document: SourceDocument, query_terms: set[str]) -> bool:
    """«Искусственный интеллект» — поле, а не зарождающийся проект."""
    return not _specific_title_tokens(document, query_terms)


def _has_project_abstract(document: SourceDocument) -> bool:
    return len((document.abstract or "").strip()) >= MIN_ABSTRACT_CHARS


def _has_artifact(document: SourceDocument) -> bool:
    return bool(ARTIFACT_RE.search(f"{document.title} {document.abstract[:2000]}"))


def _is_broad_query(query: str) -> bool:
    matched = [stem for stem in QUERY_ALIASES if stem in query.casefold()]
    return bool(matched) and all(stem in FIELD_ONLY_STEMS for stem in matched)


def _is_instrument_use(title: str, query: str) -> bool:
    """«Изучаем Y with a <прибор запроса>» — это не проект по самому прибору."""
    english = english_search_query(query)
    heads = [part for part in re.split(r"[-\s]+", english.casefold()) if len(part) >= 4]
    if not heads:
        return False
    head = heads[-1]
    if head in {"state", "intelligence"}:
        return False
    match = re.search(
        rf"\b(?:using|with|via)\s+(?:a |an |the )?(?:[\w-]+\s+){{0,4}}{re.escape(head)}s?\b",
        title,
        re.I,
    )
    if not match:
        return False
    before = title[:match.start()].casefold()
    return not re.search(rf"\b{re.escape(head)}s?\b", before)


def _is_core_project(document: SourceDocument, query: str, query_terms: set[str]) -> bool:
    """Ядро выдачи: конкретный научный проект с описанием, не обзор и не тема целиком."""
    if _is_noise_title(document) or _is_generic_topic(document, query_terms):
        return False
    if _is_instrument_use(document.title, query):
        return False
    if not _has_project_abstract(document):
        return False
    if _is_broad_query(query):
        return bool(ARTIFACT_RE.search(document.title))
    return _has_artifact(document)


def _is_recent(document: SourceDocument) -> bool:
    # Wikipedia нужна только как поддержка: дата правки не говорит о зрелости технологии.
    if document.source_type == "encyclopedia":
        return True
    if not document.published_date:
        return False
    return date.today().year - document.published_date.year <= MAX_AGE_YEARS


def _canonical_id(document: SourceDocument) -> str:
    payload = document.raw_payload if isinstance(document.raw_payload, dict) else {}
    blob = " ".join(
        str(part)
        for part in (document.external_id, document.url, payload.get("id"), payload.get("doi"), payload.get("DOI"))
        if part
    )
    doi = DOI_RE.search(blob)
    if doi:
        return f"doi:{doi.group(0).lower().rstrip('.')}"
    arxiv = ARXIV_ID_RE.search(blob)
    if arxiv:
        return f"arxiv:{arxiv.group(1)}"
    bare = re.fullmatch(r"(\d{4}\.\d{4,5})(?:v\d+)?", (document.external_id or "").strip())
    if bare:
        return f"arxiv:{bare.group(1)}"
    return f"title:{_key(document.title)}"


def _same_work(left: SourceDocument, right: SourceDocument) -> bool:
    left_id, right_id = _canonical_id(left), _canonical_id(right)
    if left_id == right_id:
        return True
    left_kind, right_kind = left_id.split(":", 1)[0], right_id.split(":", 1)[0]
    if left_kind == right_kind:
        return False
    return SequenceMatcher(None, _key(left.title), _key(right.title)).ratio() >= TITLE_SIMILARITY


def _group(documents: list[SourceDocument]) -> list[CandidateGroup]:
    groups: list[CandidateGroup] = []
    for document in documents:
        match = next(
            (
                group
                for group in groups
                if any(_same_work(existing, document) for existing in group.documents)
            ),
            None,
        )
        if match:
            match.documents.append(document)
        else:
            groups.append(CandidateGroup(documents=[document]))
    return groups


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _support_overlap(group_specific: set[str], support_specific: set[str]) -> bool:
    overlap = group_specific & support_specific
    if not overlap:
        return False
    if len(overlap) >= 2:
        return True
    if any(len(token) >= 8 for token in overlap):
        return True
    return _jaccard(group_specific, support_specific) >= SUPPORT_JACCARD


def _support_matches(group: CandidateGroup, document: SourceDocument, query_terms: set[str]) -> bool:
    """Патент и Wikipedia клеятся только к той же работе или по отличительным токенам названия."""
    if any(_same_work(existing, document) for existing in group.documents):
        return True
    support_specific = _specific_tokens(document.title, query_terms)
    if not support_specific:
        return False
    group_specific = _specific_tokens(group.title, query_terms)
    return _support_overlap(group_specific, support_specific)


def _attach_support(groups: list[CandidateGroup], support: list[SourceDocument], query_terms: set[str]) -> None:
    """Патент и Wikipedia — факторы к уже найденному проекту, не самостоятельные карточки."""
    for document in support:
        match = next((group for group in groups if _support_matches(group, document, query_terms)), None)
        if match is None or document in match.documents:
            continue
        if document.source_type == "encyclopedia":
            wiki_count = sum(1 for item in match.documents if item.source_type == "encyclopedia")
            if wiki_count >= MAX_WIKI_PER_GROUP:
                continue
        elif document.source_type == "patent":
            patent_count = sum(1 for item in match.documents if item.source_type == "patent")
            if patent_count >= MAX_PATENTS_PER_GROUP:
                continue
        match.documents.append(document)


def _has_sufficient_evidence(documents: list[SourceDocument]) -> bool:
    """Кандидат — одно научное ядро с описанием. Второй URL не обязателен."""
    return any(
        document.source_type in CORE_SOURCE_TYPES and _has_project_abstract(document)
        for document in documents
    )


def _lead_core(documents: list[SourceDocument]) -> SourceDocument:
    cores = [document for document in documents if document.source_type in CORE_SOURCE_TYPES]
    cores.sort(key=lambda item: item.published_date or date.min, reverse=True)
    return cores[0] if cores else documents[0]


def _close_topics(left: set[str], right: set[str]) -> bool:
    overlap = left & right
    return bool(overlap) and (len(overlap) >= 2 or any(len(token) >= 6 for token in overlap))


def _adoption(group: CandidateGroup, corpus: list[SourceDocument], query_terms: set[str]) -> tuple[int, list[int]]:
    """Сколько разных работ в прогоне про ту же отличительную тему — прокси распространённости."""
    specific = _specific_tokens(group.title, query_terms)
    group_key = _key(group.title)
    seen: set[str] = set()
    hits = 0
    years: list[int] = []
    for document in corpus:
        key = _key(document.title)
        if key in seen:
            continue
        other = _specific_title_tokens(document, query_terms)
        if key != group_key and not (specific and other and _close_topics(specific, other)):
            continue
        seen.add(key)
        hits += 1
        if document.published_date:
            years.append(document.published_date.year)
    return max(1, hits), sorted(years)


def _scale_mentions(corpus_hits: int) -> int:
    """Переводит частоту в прогоне на шкалу mentions, на которой училась модель (1 vs десятки тысяч)."""
    hits = max(1, corpus_hits)
    return min(MAX_ML_MENTIONS, 1 + (hits - 1) * MENTIONS_PER_EXTRA_HIT)


def _factor_map(prediction: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    for item in prediction.get("factors") or []:
        name = item.get("name")
        if not name:
            continue
        try:
            values[str(name)] = float(item.get("value") or 0)
        except (TypeError, ValueError):
            continue
    return values


def _is_strong_signal(prediction: dict, observation: dict) -> bool:
    """Сильный/зрелый сигнал не попадает в выдачу, даже если logistic saturates на academic."""
    if not prediction.get("weak_signal"):
        return True
    factors = _factor_map(prediction)
    maturity = factors.get("maturity_ratio", 0.0)
    emergence = factors.get("emergence_ratio", 0.0)
    text = f"{observation.get('title', '')} {observation.get('description', '')}"
    if COMMERCIAL_RE.search(text) and emergence < 0.008:
        return True
    return maturity > 0.01 and maturity >= max(emergence, 0.001) * 3


def _local_weakness(prediction: dict, observation: dict, corpus_hits: int, max_hits: int) -> float:
    """Относительная «слабость» внутри прогона: редкость темы + маркеры зарождения."""
    factors = _factor_map(prediction)
    emergence = min(1.0, factors.get("emergence_ratio", 0.0) * 40)
    maturity = min(1.0, factors.get("maturity_ratio", 0.0) * 40)
    novelty = factors.get("novelty", 0.5)
    rarity = 1.0 if max_hits <= 1 else max(0.0, 1.0 - (corpus_hits - 1) / max_hits)
    instrument = 0.25 if INSTRUMENT_RE.search(observation.get("title") or "") else 0.0
    return max(
        0.0,
        min(1.0, 0.38 * rarity + 0.28 * emergence + 0.22 * novelty - 0.30 * maturity - instrument),
    )


def _stretch_confidence(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lowest, highest = min(scores), max(scores)
    if highest - lowest < 1e-6:
        return [round(0.68, 4) for _ in scores]
    return [round(0.56 + 0.36 * (score - lowest) / (highest - lowest), 4) for score in scores]


def _sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 20]


def _case_example(abstract: str) -> str:
    sentences = _sentences(abstract)
    return sentences[0][:500] if sentences else ""


def _potential_benefit(abstract: str) -> str:
    for sentence in _sentences(abstract):
        if APPLICATION_RE.search(sentence):
            return sentence[:500]
    return ""


def _observation(documents: list[SourceDocument], lead: SourceDocument, mentions: int, years: list[int]) -> dict:
    source_types = [document.source_type for document in documents]
    payload = {
        "title": lead.title,
        "description": (lead.abstract or "")[:8000],
        "source_type": "academic" if "academic" in source_types else lead.source_type,
        "published_date": lead.published_date.isoformat() if lead.published_date else None,
        "has_patent": any(document.source_type == "patent" for document in documents),
        "source_trust": round(sum(document.trust for document in documents) / len(documents), 3),
        "mentions": mentions,
    }
    if len(set(years)) >= 2:
        counts = Counter(years)
        payload["mentions_series"] = [float(counts[year]) for year in sorted(counts)]
    return payload


def _predict(observation: dict) -> dict:
    payload = json.dumps({"observations": [observation], "top_n": 1}).encode("utf-8")
    request = Request(
        f"{ML_SERVICE_URL}/predict", data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["predictions"][0]


def build_candidates(run: SearchRun, industry_filter: str | None = None) -> tuple[int, int, int, list[str]]:
    """Фильтрует и ранжирует не более 15 подтверждённых слабых сигналов."""
    query_terms = _query_terms(run.query)
    selected_documents = [
        document for document in run.documents.all().order_by("-published_date")
        if _is_recent(document) and _is_relevant(document, run.query, query_terms)
    ]
    core_documents = [
        document for document in selected_documents
        if document.source_type in CORE_SOURCE_TYPES and _is_core_project(document, run.query, query_terms)
    ]
    support_documents = [
        document for document in selected_documents
        if document.source_type in SUPPORT_SOURCE_TYPES and not _is_noise_title(document)
    ]
    grouped = _group(core_documents)
    _attach_support(grouped, support_documents, query_terms)
    grouped = [group for group in grouped if _has_sufficient_evidence(group.documents)]

    run.candidates.all().delete()
    errors: list[str] = []
    if query_needs_translation(run.query):
        errors.append("query_not_translated: нет английского соответствия запроса")
    created_count = weak_count = high_confidence_count = 0
    scored: list[tuple[dict, SourceDocument, list[SourceDocument], str, int, dict]] = []
    for group in grouped:
        documents = group.documents
        lead = _lead_core(documents)
        corpus_hits, years = _adoption(group, core_documents, query_terms)
        observation = _observation(documents, lead, _scale_mentions(corpus_hits), years)
        try:
            prediction = _predict(observation)
        except Exception as error:
            errors.append(f"ML: {error}")
            continue
        if _is_strong_signal(prediction, observation):
            continue
        core_categories: list[str] = []
        for document in documents:
            if document.source_type in CORE_SOURCE_TYPES:
                core_categories.extend(document.categories or [])
        predicted_industry = _categories_to_industry(core_categories) or TechnologyCandidate.Industry.OTHER.value
        if industry_filter and predicted_industry != industry_filter:
            continue
        scored.append((prediction, lead, documents, predicted_industry, corpus_hits, observation))

    if not scored:
        if run.documents.count() >= 20:
            errors.append(
                "no_projects_after_filters: "
                f"sources={run.documents.count()} relevant={len(selected_documents)} "
                f"core={len(core_documents)}"
            )
        return created_count, weak_count, high_confidence_count, errors
    ml_ranked = sorted(scored, key=lambda item: item[0]["confidence"], reverse=True)[:MAX_CANDIDATES]
    ml_scores = [item[0]["confidence"] for item in ml_ranked]
    use_local = len(ml_ranked) >= 2 and (
        max(ml_scores) - min(ml_scores) < 0.05 or min(ml_scores) >= 0.75
    )
    max_hits = max(item[4] for item in ml_ranked)
    local_scores = [
        _local_weakness(item[0], item[5], item[4], max_hits) for item in ml_ranked
    ]
    display_scores = _stretch_confidence(local_scores) if use_local else ml_scores
    ranked = sorted(
        zip(ml_ranked, display_scores),
        key=lambda item: item[1],
        reverse=True,
    )
    high_slots = min(4, max(1, len(ranked) // 4))
    for index, ((prediction, lead, documents, predicted_industry, _hits, _obs), confidence) in enumerate(ranked):
        is_high = index < high_slots
        candidate = TechnologyCandidate.objects.create(
            run=run,
            title=lead.title,
            description=(lead.abstract or "")[:4000],
            potential_benefit=_potential_benefit(lead.abstract or ""),
            case_example=_case_example(lead.abstract or ""),
            confidence=confidence,
            is_weak_signal=True,
            is_high_confidence=is_high,
            explanation=prediction["explanation"],
            factors=prediction["factors"],
            industry=predicted_industry,
        )
        candidate.source_documents.set(documents)
        created_count += 1
        weak_count += int(candidate.is_weak_signal)
        high_confidence_count += int(candidate.is_high_confidence)
    return created_count, weak_count, high_confidence_count, errors
