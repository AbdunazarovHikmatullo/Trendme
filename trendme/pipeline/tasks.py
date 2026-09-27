"""Оркестрация Celery-конвейера поиска и анализа."""

from celery import chord, group, shared_task
from django.utils import timezone

from parser.tasks import (
    fetch_arxiv,
    fetch_crossref,
    fetch_europepmc,
    fetch_google_patents,
    fetch_openalex,
    fetch_wikipedia,
)

from .models import SearchRun
from .services import build_candidates


@shared_task
def start_search(run_id: str) -> None:
    run = SearchRun.objects.get(pk=run_id)
    run.status = SearchRun.Status.FETCHING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    chord(
        group(
            fetch_openalex.s(run_id, run.query),
            fetch_arxiv.s(run_id, run.query),
            fetch_google_patents.s(run_id, run.query),
            fetch_wikipedia.s(run_id, run.query),
            fetch_crossref.s(run_id, run.query),
            fetch_europepmc.s(run_id, run.query),
        )
    )(finalize_search.s(run_id))


@shared_task
def finalize_search(fetch_results: list[dict], run_id: str) -> None:
    run = SearchRun.objects.get(pk=run_id)
    run.status = SearchRun.Status.ANALYZING
    run.save(update_fields=["status"])
    fetch_errors = [result["error"] for result in fetch_results if result.get("error")]
    try:
        industry = run.industry_filter or None
        count, weak, high, ml_errors = build_candidates(run, industry_filter=industry)
        run.processed_sources = run.documents.count()
        run.candidates_count = count
        run.weak_signals_count = weak
        run.high_confidence_count = high
        run.errors = fetch_errors + ml_errors
        run.status = SearchRun.Status.PARTIAL if run.errors else SearchRun.Status.COMPLETED
    except Exception as error:
        run.errors = fetch_errors + [str(error)]
        run.status = SearchRun.Status.FAILED
    run.completed_at = timezone.now()
    run.save()
