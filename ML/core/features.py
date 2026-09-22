"""Извлечение интерпретируемых факторов (признаков) из наблюдения."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from .preprocessing import normalize_for_markers
from .signals import (
    DEFAULT_SOURCE_TRUST,
    EARLY_SOURCE_TYPES,
    EMERGENCE_MARKERS,
    HYPE_MARKERS,
    MATURITY_MARKERS,
    SOURCE_TRUST,
)

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_CURRENT_YEAR = 2026


@dataclass
class Factor:
    name: str
    value: float
    direction: int
    description: str
    weight: float = 0.0
    contribution: float = 0.0


FACTOR_LABELS = {
    "emergence_ratio": "Доля маркеров зарождения",
    "maturity_ratio": "Доля маркеров зрелости",
    "hype_ratio": "Доля маркетинговых/хайповых маркеров",
    "source_trust": "Уровень доверия к источнику",
    "early_source": "Ранний тип источника (патент/наука)",
    "has_patent": "Наличие патента/заявки",
    "has_investment": "Наличие инвестиций",
    "novelty": "Новизна (свежесть публикации)",
    "low_adoption": "Низкая распространённость",
    "growth_rate": "Рост упоминаний",
}

NEUTRAL_VALUES = {
    "emergence_ratio": 0.0,
    "maturity_ratio": 0.0,
    "hype_ratio": 0.0,
    "source_trust": 0.5,
    "early_source": 0.0,
    "has_patent": 0.0,
    "has_investment": 0.0,
    "novelty": 0.5,
    "low_adoption": 0.5,
    "growth_rate": 0.5,
}


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _parse_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        year = int(value)
        return year if 1950 <= year <= _CURRENT_YEAR + 1 else None
    match = _YEAR_RE.search(str(value))
    return int(match.group()) if match else None


def normalize_observation(obs: Any) -> Dict[str, Any]:
    if isinstance(obs, dict):
        data = dict(obs)
    else:
        data = obs.model_dump() if hasattr(obs, "model_dump") else dict(vars(obs))

    source = data.get("source") or {}
    if not isinstance(source, dict):
        source = source.model_dump() if hasattr(source, "model_dump") else {}

    title = _first(data.get("title"), data.get("name"))
    description = _first(
        data.get("description"), data.get("text"),
        data.get("summary"), data.get("abstract"),
    )

    return {
        "title": title or "",
        "description": description or "",
        "published_date": _first(data.get("published_date"), data.get("date"), source.get("date")),
        "first_seen": data.get("first_seen"),
        "source_type": _first(data.get("source_type"), source.get("type"), data.get("type")),
        "source_name": _first(data.get("source_name"), source.get("name")),
        "source_url": _first(data.get("source_url"), source.get("url"), data.get("url")),
        "language": _first(data.get("language"), source.get("language")),
        "source_trust": _first(data.get("source_trust"), source.get("trust"), data.get("trust")),
        "mentions": _first(data.get("mentions"), data.get("frequency"), data.get("occurrences")),
        "mentions_series": data.get("mentions_series"),
        "has_patent": _first(data.get("has_patent"), data.get("patent"), data.get("patents"), data.get("patent_count")),
        "has_investment": _first(
            data.get("has_investment"), data.get("investment"),
            data.get("investments"), data.get("funding"), data.get("investment_amount"),
        ),
    }


class FeatureExtractor:
    NUMERIC_FEATURES = [
        "emergence_ratio",
        "maturity_ratio",
        "hype_ratio",
        "source_trust",
        "early_source",
        "has_patent",
        "has_investment",
        "novelty",
        "low_adoption",
        "growth_rate",
    ]

    def text(self, obs: Dict[str, Any]) -> str:
        return f"{obs['title']} {obs['description']}".strip()

    def _ratio(self, normalized: str, markers: List[str]) -> float:
        tokens = max(1, len(normalized.split()))
        hits = sum(normalized.count(marker) for marker in markers)
        return min(1.0, hits / tokens)

    def _source_trust(self, obs: Dict[str, Any]) -> float:
        explicit = obs.get("source_trust")
        if explicit is not None:
            try:
                return max(0.0, min(1.0, float(explicit)))
            except (TypeError, ValueError):
                pass
        source_type = str(obs.get("source_type") or "").lower().strip()
        source_type = re.sub(r"[\s-]+", "_", source_type)
        return SOURCE_TRUST.get(source_type, DEFAULT_SOURCE_TRUST)

    def _early_source(self, obs: Dict[str, Any]) -> float:
        source_type = str(obs.get("source_type") or "").lower().strip()
        source_type = re.sub(r"[\s-]+", "_", source_type)
        return 1.0 if source_type in EARLY_SOURCE_TYPES else 0.0

    def _flag(self, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return 1.0 if float(value) > 0 else 0.0
        text = str(value).strip().lower()
        if text in ("", "0", "false", "no", "нет", "none", "nan", "null", "-"):
            return 0.0
        return 1.0

    def _has_patent(self, obs: Dict[str, Any]) -> float:
        return self._flag(obs.get("has_patent"))

    def _has_investment(self, obs: Dict[str, Any]) -> float:
        return self._flag(obs.get("has_investment"))

    def _novelty(self, obs: Dict[str, Any]) -> float:
        year = _parse_year(obs.get("first_seen") or obs.get("published_date"))
        if year is None:
            return 0.5
        return max(0.0, min(1.0, (year - 1990) / (_CURRENT_YEAR - 1990)))

    def _low_adoption(self, obs: Dict[str, Any]) -> float:
        mentions = obs.get("mentions")
        if mentions is None:
            return 0.5
        try:
            mentions = max(0.0, float(mentions))
        except (TypeError, ValueError):
            return 0.5
        adoption = min(1.0, math.log1p(mentions) / math.log1p(10000))
        return 1.0 - adoption

    def _growth_rate(self, obs: Dict[str, Any]) -> float:
        series = obs.get("mentions_series")
        if not isinstance(series, (list, tuple)) or len(series) < 2:
            return 0.5
        try:
            values = [float(x) for x in series]
        except (TypeError, ValueError):
            return 0.5
        first = max(0.0, values[0])
        last = max(0.0, values[-1])
        base = max(first, 1.0)
        growth = (last - first) / base
        return 1.0 / (1.0 + math.exp(-growth))

    def extract_features(self, obs: Dict[str, Any]) -> Dict[str, float]:
        text = self.text(obs)
        normalized = normalize_for_markers(text)
        return {
            "emergence_ratio": self._ratio(normalized, EMERGENCE_MARKERS),
            "maturity_ratio": self._ratio(normalized, MATURITY_MARKERS),
            "hype_ratio": self._ratio(normalized, HYPE_MARKERS),
            "source_trust": self._source_trust(obs),
            "early_source": self._early_source(obs),
            "has_patent": self._has_patent(obs),
            "has_investment": self._has_investment(obs),
            "novelty": self._novelty(obs),
            "low_adoption": self._low_adoption(obs),
            "growth_rate": self._growth_rate(obs),
        }

    def extract_factors(self, obs: Dict[str, Any], directions: Dict[str, int]) -> List[Factor]:
        features = self.extract_features(obs)
        factors = []
        for name in self.NUMERIC_FEATURES:
            factors.append(
                Factor(
                    name=name,
                    value=round(features[name], 4),
                    direction=int(directions.get(name, 0)),
                    description=FACTOR_LABELS[name],
                )
            )
        factors.sort(key=lambda f: -abs(f.value - NEUTRAL_VALUES[f.name]))
        return factors
