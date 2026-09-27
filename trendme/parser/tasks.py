"""Celery-задачи получения документов из независимых открытых источников."""

from celery import shared_task

from .models import SourceDocument
from .services import arxiv, crossref, europepmc, google_patents, openalex, wikipedia


def _store(run_id: str, documents: list[dict]) -> int:
    stored = 0
    for document in documents:
        _, created = SourceDocument.objects.update_or_create(
            run_id=run_id, provider=document["provider"], external_id=document["external_id"], defaults=document,
        )
        stored += int(created)
    return stored


@shared_task
def fetch_openalex(run_id: str, query: str) -> dict:
    try:
        return {"provider": "openalex", "stored": _store(run_id, openalex(query))}
    except Exception as error:
        return {"provider": "openalex", "stored": 0, "error": f"openalex: {error}"}


@shared_task
def fetch_arxiv(run_id: str, query: str) -> dict:
    try:
        return {"provider": "arxiv", "stored": _store(run_id, arxiv(query))}
    except Exception as error:
        return {"provider": "arxiv", "stored": 0, "error": f"arxiv: {error}"}


@shared_task
def fetch_google_patents(run_id: str, query: str) -> dict:
    try:
        return {"provider": "google_patents", "stored": _store(run_id, google_patents(query))}
    except Exception as error:
        return {"provider": "google_patents", "stored": 0, "error": f"google_patents: {error}"}


@shared_task
def fetch_wikipedia(run_id: str, query: str) -> dict:
    try:
        return {"provider": "wikipedia", "stored": _store(run_id, wikipedia(query))}
    except Exception as error:
        return {"provider": "wikipedia", "stored": 0, "error": f"wikipedia: {error}"}


@shared_task
def fetch_crossref(run_id: str, query: str) -> dict:
    try:
        return {"provider": "crossref", "stored": _store(run_id, crossref(query))}
    except Exception as error:
        return {"provider": "crossref", "stored": 0, "error": f"crossref: {error}"}


@shared_task
def fetch_europepmc(run_id: str, query: str) -> dict:
    try:
        return {"provider": "europepmc", "stored": _store(run_id, europepmc(query))}
    except Exception as error:
        return {"provider": "europepmc", "stored": 0, "error": f"europepmc: {error}"}
