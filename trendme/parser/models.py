from django.db import models


class SourceDocument(models.Model):
    """Нормализованный документ, полученный из открытого проверяемого источника."""

    run = models.ForeignKey("pipeline.SearchRun", on_delete=models.CASCADE, related_name="documents")
    provider = models.CharField(max_length=32)
    external_id = models.CharField(max_length=512)
    title = models.TextField()
    abstract = models.TextField(blank=True)
    url = models.URLField(max_length=1000)
    published_date = models.DateField(null=True, blank=True)
    source_name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=32)
    language = models.CharField(max_length=16, blank=True)
    trust = models.FloatField()
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "provider", "external_id"], name="unique_document_per_run"),
        ]
        indexes = [models.Index(fields=["run", "provider"]), models.Index(fields=["published_date"])]

    def __str__(self) -> str:
        return self.title[:100]
