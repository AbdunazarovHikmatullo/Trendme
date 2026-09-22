import uuid

from django.db import models


class SearchRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "В очереди"
        FETCHING = "fetching", "Сбор источников"
        ANALYZING = "analyzing", "Анализ кандидатов"
        COMPLETED = "completed", "Готово"
        PARTIAL = "partial", "Готово с ошибками источников"
        FAILED = "failed", "Ошибка"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.CharField(max_length=300)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    processed_sources = models.PositiveIntegerField(default=0)
    candidates_count = models.PositiveIntegerField(default=0)
    weak_signals_count = models.PositiveIntegerField(default=0)
    high_confidence_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class TechnologyCandidate(models.Model):
    run = models.ForeignKey(SearchRun, on_delete=models.CASCADE, related_name="candidates")
    title = models.TextField()
    description = models.TextField(blank=True)
    potential_benefit = models.TextField(blank=True)
    case_example = models.TextField(blank=True)
    confidence = models.FloatField(default=0)
    is_weak_signal = models.BooleanField(default=False)
    is_high_confidence = models.BooleanField(default=False)
    explanation = models.TextField(blank=True)
    factors = models.JSONField(default=list, blank=True)
    source_documents = models.ManyToManyField("parser.SourceDocument", related_name="candidates")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-confidence", "title"]
        indexes = [models.Index(fields=["run", "is_weak_signal", "confidence"])]
