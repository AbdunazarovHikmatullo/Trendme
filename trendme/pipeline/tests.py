from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from parser.models import SourceDocument

from .models import SearchRun
from .tasks import finalize_search


class PipelineTests(TestCase):
    def setUp(self) -> None:
        self.run = SearchRun.objects.create(query="квантовые сенсоры")
        SourceDocument.objects.create(
            run=self.run,
            provider="openalex",
            external_id="https://doi.org/10.1000/example",
            title="Laboratory quantum sensor prototype",
            abstract="Early research prototype with a pilot deployment.",
            url="https://doi.org/10.1000/example",
            published_date=date(2026, 1, 1),
            source_name="OpenAlex",
            source_type="academic",
            language="en",
            trust=0.95,
        )
        SourceDocument.objects.create(
            run=self.run,
            provider="arxiv",
            external_id="http://arxiv.org/abs/2601.00001",
            title="Laboratory quantum sensor prototype",
            abstract="Early research prototype with a pilot deployment.",
            url="http://arxiv.org/abs/2601.00001",
            published_date=date(2026, 1, 2),
            source_name="arXiv",
            source_type="preprint",
            language="en",
            trust=0.85,
        )

    @patch("pipeline.services._predict")
    def test_finalize_builds_explainable_candidate(self, predict_mock) -> None:
        predict_mock.return_value = {
            "confidence": 0.91,
            "weak_signal": True,
            "explanation": "в пользу слабого сигнала: ранний тип источника (1.00).",
            "factors": [{"name": "early_source", "value": 1.0, "direction": 1, "description": "Ранний тип источника", "weight": 1.0, "contribution": 1.0}],
        }
        finalize_search.run([], str(self.run.id))
        self.run.refresh_from_db()
        candidate = self.run.candidates.get()
        self.assertEqual(self.run.status, SearchRun.Status.COMPLETED)
        self.assertEqual(self.run.processed_sources, 2)
        self.assertEqual(self.run.weak_signals_count, 1)
        self.assertEqual(candidate.confidence, 0.91)
        self.assertEqual(candidate.source_documents.count(), 2)

    @patch("pipeline.services._predict")
    def test_rejects_old_or_unconfirmed_documents(self, predict_mock) -> None:
        SourceDocument.objects.create(
            run=self.run,
            provider="openalex",
            external_id="https://doi.org/10.1000/old",
            title="Quantum sensor review",
            abstract="Quantum sensor research.",
            url="https://doi.org/10.1000/old",
            published_date=date(2014, 1, 1),
            source_name="OpenAlex",
            source_type="academic",
            language="en",
            trust=0.95,
        )
        SourceDocument.objects.create(
            run=self.run,
            provider="openalex",
            external_id="https://doi.org/10.1000/ufo",
            title="UFO observations and astronomy",
            abstract="Quantum sensors are mentioned only as a possible tool.",
            url="https://doi.org/10.1000/ufo",
            published_date=date(2026, 1, 1),
            source_name="OpenAlex",
            source_type="academic",
            language="en",
            trust=0.95,
        )
        predict_mock.return_value = {
            "confidence": 0.91, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 1)
        self.assertEqual(self.run.candidates.get().title, "Laboratory quantum sensor prototype")

    @patch("pipeline.services._predict")
    def test_keeps_only_top_fifteen_candidates(self, predict_mock) -> None:
        names = [
            "alpha", "bravo", "charlie", "delta", "echoes", "foxtrot", "golfing", "hotel", "india", "juliet",
            "kiloone", "limaone", "mikeone", "november", "oscarone", "papaya",
        ]
        for index, name in enumerate(names):
            for provider, source_type in (("openalex", "academic"), ("arxiv", "preprint")):
                SourceDocument.objects.create(
                    run=self.run,
                    provider=provider,
                    external_id=f"{provider}-{index}",
                    title=f"Quantum sensor prototype {name}",
                    abstract="Quantum sensor prototype for early research.",
                    url=f"https://example.org/{provider}/{index}",
                    published_date=date(2026, 2, 1),
                    source_name=provider,
                    source_type=source_type,
                    language="en",
                    trust=0.9,
                )
        predict_mock.return_value = {
            "confidence": 0.91, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 15)

    @patch("pipeline.views.start_search.delay")
    def test_create_search_enqueues_background_work(self, delay_mock) -> None:
        response = APIClient().post("/api/searches/", {"query": "перспективные решения в финтехе"}, format="json")
        self.assertEqual(response.status_code, 202)
        run = SearchRun.objects.get(pk=response.data["id"])
        self.assertEqual(run.status, SearchRun.Status.QUEUED)
        delay_mock.assert_called_once_with(str(run.id))

    def test_search_query_is_validated(self) -> None:
        response = APIClient().post("/api/searches/", {"query": " "}, format="json")
        self.assertEqual(response.status_code, 400)

    @patch("pipeline.services._predict")
    def test_keeps_patent_and_wikipedia_sources(self, predict_mock) -> None:
        SourceDocument.objects.create(
            run=self.run,
            provider="google_patents",
            external_id="US11988619B2",
            title="Microwave-free quantum sensor based on NV centers",
            abstract="A quantum sensor prototype for early laboratory research.",
            url="https://patents.google.com/patent/US11988619B2",
            published_date=date(2025, 3, 1),
            source_name="Google Patents",
            source_type="patent",
            language="en",
            trust=0.95,
        )
        SourceDocument.objects.create(
            run=self.run,
            provider="wikipedia",
            external_id="en:123",
            title="Quantum sensor",
            abstract="A quantum sensor is a device that exploits quantum correlations.",
            url="https://en.wikipedia.org/wiki/Quantum_sensor",
            published_date=date(2026, 1, 15),
            source_name="Wikipedia",
            source_type="encyclopedia",
            language="en",
            trust=0.75,
        )
        predict_mock.return_value = {
            "confidence": 0.88, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        providers = {
            source.provider
            for candidate in self.run.candidates.all()
            for source in candidate.source_documents.all()
        }
        self.assertIn("google_patents", providers)
        self.assertIn("wikipedia", providers)
