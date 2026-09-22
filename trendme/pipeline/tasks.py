"""Оркестрация Celery-конвейера поиска и анализа."""

from celery import chord, group, shared_task
from django.utils import timezone

from parser.tasks import fetch_arxiv, fetch_openalex

from .models import SearchRun
from .services import build_candidates


@shared_task
def start_search(run_id: str) -> None:
    run = SearchRun.objects.get(pk=run_id)
    run.status = SearchRun.Status.FETCHING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    chord(group(fetch_openalex.s(run_id, run.query), fetch_arxiv.s(run_id, run.query)))(finalize_search.s(run_id))


@shared_task
def finalize_search(fetch_results: list[dict], run_id: str) -> None:
    run = SearchRun.objects.get(pk=run_id)
    run.status = SearchRun.Status.ANALYZING
    run.save(update_fields=["status"])
    fetch_errors = [result["error"] for result in fetch_results if result.get("error")]
    try:
        count, weak, high, ml_errors = build_candidates(run)
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
