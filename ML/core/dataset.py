"""Загрузка датасетов: слабые сигналы (xlsx) + зрелые технологии (csv)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

import pandas as pd

FUND_PATTERN = re.compile(r"\$\d|€\d|млн|млрд|seed|series|pre-seed|раунд|оценк|инвест", re.IGNORECASE)
PATENT_PATTERN = re.compile(r"патент|patent", re.IGNORECASE)
INVESTOR_PATTERN = re.compile(r"invest|ventures|capital|partners", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b(20(?:1\d|2[0-6]))\b")

ACADEMIC_DOMAINS = {
    "arxiv", "nature", "mdpi", "sciencedirect", "ieee", "springer",
    "researchgate", "acm", "journals", "science", "sciencedaily", "cell",
}


def _source_domains(sources: Any) -> set[str]:
    return set(re.findall(r"https?://([^/)\]]+)", str(sources)))


def _academic_source(sources: Any) -> bool:
    domains = " ".join(_source_domains(sources)).lower()
    return any(domain in domains for domain in ACADEMIC_DOMAINS)


def _latest_year(sources: Any) -> int | None:
    years = [int(y) for y in YEAR_PATTERN.findall(str(sources))]
    return max(years) if years else None


def load_weak_signals(path: Any) -> Tuple[List[Dict[str, Any]], List[int]]:
    """Читает xlsx со слабыми сигналами. Возвращает (observations, bally)."""
    df = pd.read_excel(path, sheet_name=0, header=1)
    df = df.dropna(subset=["Технология (слабый сигнал)"])

    observations: List[Dict[str, Any]] = []
    bally: List[int] = []
    for _, row in df.iterrows():
        why = str(row["Почему это слабый сигнал"])
        companies = str(row["Компании"])
        sources = str(row["Источники"])
        has_investment = bool(FUND_PATTERN.search(why)) or bool(INVESTOR_PATTERN.search(companies))
        has_patent = bool(PATENT_PATTERN.search(why))
        year = _latest_year(sources)
        source_type = (
            "academic" if _academic_source(sources)
            else "media" if _source_domains(sources) else "other"
        )
        observations.append({
            "title": str(row["Технология (слабый сигнал)"]),
            "description": f"{why} {row['Стадия развития']} {row['Тренд упоминаний']}",
            "source_type": source_type,
            "published_date": f"{year}-01-01" if year else None,
            "has_investment": has_investment,
            "has_patent": has_patent,
            "mentions": len(_source_domains(sources)),
            "domain": str(row["Область"]),
        })
        bally.append(int(row["Балл (стадия+тренд)"]))
    return observations, bally


def load_mature(path: Any) -> List[Dict[str, Any]]:
    """Читает csv со зрелыми технологиями. Возвращает observations."""
    df = pd.read_csv(path)
    observations: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        description = str(row["description"])
        observations.append({
            "title": str(row["title"]),
            "description": description,
            "source_type": str(row["source_type"]),
            "published_date": str(row["published_date"]),
            "first_seen": row["first_seen"],
            "mentions": row["mentions"],
            "has_investment": bool(FUND_PATTERN.search(description)),
            "has_patent": bool(PATENT_PATTERN.search(description)),
            "domain": str(row["domain"]),
        })
    return observations


def load_dataset(weak_path: Any, mature_path: Any) -> Dict[str, Any]:
    weak_obs, bally = load_weak_signals(weak_path)
    mature_obs = load_mature(mature_path)

    observations = weak_obs + mature_obs
    labels = [1] * len(weak_obs) + [0] * len(mature_obs)
    bally_full = bally + [None] * len(mature_obs)

    return {
        "observations": observations,
        "labels": labels,
        "bally": bally_full,
        "n_weak": len(weak_obs),
        "n_mature": len(mature_obs),
    }
