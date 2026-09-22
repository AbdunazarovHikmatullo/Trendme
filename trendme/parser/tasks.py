"""Celery-задачи получения документов из независимых открытых источников."""

from celery import shared_task

from .models import SourceDocument
from .services import arxiv, openalex


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
    except Exception as error:  # ошибка одного источника не отменяет весь поиск
        return {"provider": "openalex", "stored": 0, "error": str(error)}


@shared_task
def fetch_arxiv(run_id: str, query: str) -> dict:
    try:
        return {"provider": "arxiv", "stored": _store(run_id, arxiv(query))}
    except Exception as error:  # ошибка одного источника не отменяет весь поиск
        return {"provider": "arxiv", "stored": 0, "error": str(error)}
