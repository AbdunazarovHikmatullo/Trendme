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
            abstract="Early research prototype of a laboratory quantum sensor with a pilot deployment and experimental readout.",
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
            abstract="Early research prototype of a laboratory quantum sensor with a pilot deployment and experimental readout.",
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
                    abstract="Quantum sensor prototype for early laboratory research and experimental validation of the sensing method.",
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
    def test_attaches_matching_patent_but_not_generic_wiki(self, predict_mock) -> None:
        self.run.documents.all().delete()
        SourceDocument.objects.create(
            run=self.run,
            provider="openalex",
            external_id="https://doi.org/10.1000/nv",
            title="Laboratory nv-center quantum sensor prototype",
            abstract="We report an early laboratory prototype of an nv-center quantum sensor with experimental readout.",
            url="https://doi.org/10.1000/nv",
            published_date=date(2026, 1, 1),
            source_name="OpenAlex",
            source_type="academic",
            language="en",
            trust=0.95,
        )
        SourceDocument.objects.create(
            run=self.run,
            provider="google_patents",
            external_id="US11988619B2",
            title="Microwave-free nv-center quantum sensor prototype",
            abstract="A quantum sensor prototype for early laboratory research based on nitrogen-vacancy centers.",
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
        candidate = self.run.candidates.get()
        providers = {source.provider for source in candidate.source_documents.all()}
        self.assertIn("google_patents", providers)
        self.assertNotIn("wikipedia", providers)

    @patch("pipeline.services._predict")
    def test_skips_strong_signal(self, predict_mock) -> None:
        predict_mock.return_value = {
            "confidence": 0.21, "weak_signal": False, "explanation": "зрелый сигнал", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)

    @patch("pipeline.services._predict")
    def test_wikipedia_or_patent_alone_is_not_a_project(self, predict_mock) -> None:
        self.run.documents.all().delete()
        SourceDocument.objects.create(
            run=self.run,
            provider="wikipedia",
            external_id="en:list",
            title="List of sensors",
            abstract="A list of sensor types.",
            url="https://en.wikipedia.org/wiki/List_of_sensors",
            published_date=date(2026, 1, 15),
            source_name="Wikipedia",
            source_type="encyclopedia",
            language="en",
            trust=0.75,
        )
        SourceDocument.objects.create(
            run=self.run,
            provider="google_patents",
            external_id="US1",
            title="Quantum sensor device",
            abstract="A patented quantum sensor.",
            url="https://patents.google.com/patent/US1",
            published_date=date(2025, 1, 1),
            source_name="Google Patents",
            source_type="patent",
            language="en",
            trust=0.95,
        )
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)
        predict_mock.assert_not_called()

    @patch("pipeline.services._predict")
    def test_skips_education_conference_and_empty_abstract(self, predict_mock) -> None:
        self.run.query = "Искусственный интеллект"
        self.run.save(update_fields=["query"])
        self.run.documents.all().delete()
        samples = (
            (
                "openalex",
                "edu-1",
                "Искусственный интеллект в образовании: вызов современности или будущее педагогики?",
                "В статье рассматривается роль искусственного интеллекта в современном образовании и персонализации обучения.",
            ),
            (
                "crossref",
                "edu-2",
                "Искусственный интеллект в образовании: вызов современности или будущее педагогики?",
                "В статье рассматривается роль искусственного интеллекта в современном образовании и персонализации обучения.",
            ),
            (
                "openalex",
                "conf-1",
                "Вторая конференция «Искусственный интеллект в химии и материаловедении»",
                "Ученые обсуждали, можно ли научить нейросеть узнавать структуру вещества по фотографии кристаллов.",
            ),
            (
                "crossref",
                "empty-1",
                "Как измерить искусственный интеллект?",
                "",
            ),
            (
                "openalex",
                "empty-2",
                "Как измерить искусственный интеллект?",
                "",
            ),
            (
                "arxiv",
                "review-1",
                "Games for Artificial Intelligence Research: A Review and Perspectives",
                "This article reviews games used as benchmarks for artificial intelligence research and future perspectives.",
            ),
        )
        for provider, external_id, title, abstract in samples:
            SourceDocument.objects.create(
                run=self.run,
                provider=provider,
                external_id=external_id,
                title=title,
                abstract=abstract,
                url=f"https://example.org/{external_id}",
                published_date=date(2025, 3, 1),
                source_name=provider,
                source_type="academic",
                language="ru",
                trust=0.9,
            )
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)
        predict_mock.assert_not_called()

    @patch("pipeline.services._predict")
    def test_keeps_specific_emerging_ai_project(self, predict_mock) -> None:
        self.run.query = "Искусственный интеллект"
        self.run.save(update_fields=["query"])
        self.run.documents.all().delete()
        title = "Photonic neural accelerator for early artificial intelligence inference"
        abstract = "We report an early laboratory prototype of a photonic neural accelerator for on-device inference."
        for provider, source_type, external_id in (
            ("openalex", "academic", "oa-ai-1"),
            ("arxiv", "preprint", "arxiv-ai-1"),
        ):
            SourceDocument.objects.create(
                run=self.run,
                provider=provider,
                external_id=external_id,
                title=title,
                abstract=abstract,
                url=f"https://example.org/{external_id}",
                published_date=date(2026, 2, 1),
                source_name=provider,
                source_type=source_type,
                language="en",
                trust=0.9,
            )
        predict_mock.return_value = {
            "confidence": 0.82, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 1)
        self.assertEqual(self.run.candidates.get().title, title)

    @patch("pipeline.services._predict")
    def test_does_not_merge_unrelated_ai_papers(self, predict_mock) -> None:
        self.run.query = "Искусственный интеллект"
        self.run.save(update_fields=["query"])
        self.run.documents.all().delete()
        papers = (
            "Photonic neural accelerator for early artificial intelligence inference",
            "Atomic magnetometer prototype using artificial intelligence readout",
        )
        abstract = "Early research prototype with neural network methods and laboratory data analysis."
        for index, title in enumerate(papers):
            for provider, source_type in (("openalex", "academic"), ("arxiv", "preprint")):
                SourceDocument.objects.create(
                    run=self.run,
                    provider=provider,
                    external_id=f"{provider}-{index}",
                    title=title,
                    abstract=abstract,
                    url=f"https://example.org/{provider}/{index}",
                    published_date=date(2026, 2, 1),
                    source_name=provider,
                    source_type=source_type,
                    language="en",
                    trust=0.9,
                )
        predict_mock.return_value = {
            "confidence": 0.8, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        titles = set(self.run.candidates.values_list("title", flat=True))
        self.assertEqual(titles, set(papers))

    @patch("pipeline.services._predict")
    def test_does_not_merge_different_arxiv_papers(self, predict_mock) -> None:
        self.run.documents.all().delete()
        papers = (
            ("http://arxiv.org/abs/2404.18293", "Quantum learning with a single-atom sensor prototype"),
            ("http://arxiv.org/abs/2606.15071", "Muonium spectroscopy with a laboratory quantum sensor device"),
        )
        abstract = "We report an experimental prototype of a laboratory quantum sensor device with readout electronics."
        for external_id, title in papers:
            SourceDocument.objects.create(
                run=self.run,
                provider="arxiv",
                external_id=external_id,
                title=title,
                abstract=abstract,
                url=external_id,
                published_date=date(2026, 2, 1),
                source_name="arXiv",
                source_type="preprint",
                language="en",
                trust=0.85,
            )
        predict_mock.return_value = {
            "confidence": 0.8, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        titles = set(self.run.candidates.values_list("title", flat=True))
        self.assertEqual(titles, {title for _, title in papers})

    @patch("pipeline.services._predict")
    def test_unrelated_patent_is_not_attached(self, predict_mock) -> None:
        SourceDocument.objects.create(
            run=self.run,
            provider="google_patents",
            external_id="US-UNRELATED",
            title="Quantum sensor array for industrial metrology calibration",
            abstract="A patented quantum sensor unrelated to the laboratory prototype paper.",
            url="https://patents.google.com/patent/US-UNRELATED",
            published_date=date(2025, 1, 1),
            source_name="Google Patents",
            source_type="patent",
            language="en",
            trust=0.95,
        )
        predict_mock.return_value = {
            "confidence": 0.8, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        providers = {
            source.provider
            for candidate in self.run.candidates.all()
            for source in candidate.source_documents.all()
        }
        self.assertNotIn("google_patents", providers)

    @patch("pipeline.services._predict")
    def test_rejects_offtopic_blockchain_and_routing(self, predict_mock) -> None:
        self.run.documents.all().delete()
        samples = (
            "Post-Quantum Sensor-to-Blockchain Communication Security",
            "Energy Efficient Sensor Network Routing using A Quantum Processor",
        )
        abstract = "We report an experimental prototype of a quantum sensor device for laboratory use."
        for index, title in enumerate(samples):
            SourceDocument.objects.create(
                run=self.run,
                provider="arxiv",
                external_id=f"http://arxiv.org/abs/2601.1000{index}",
                title=title,
                abstract=abstract,
                url=f"http://arxiv.org/abs/2601.1000{index}",
                published_date=date(2026, 2, 1),
                source_name="arXiv",
                source_type="preprint",
                language="en",
                trust=0.85,
            )
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)
        predict_mock.assert_not_called()

    @patch("pipeline.services._predict")
    def test_single_core_paper_is_enough(self, predict_mock) -> None:
        self.run.documents.exclude(provider="openalex").delete()
        predict_mock.return_value = {
            "confidence": 0.82, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        candidate = self.run.candidates.get()
        self.assertEqual(candidate.source_documents.count(), 1)
        self.assertEqual(candidate.title, "Laboratory quantum sensor prototype")

    @patch("pipeline.services._predict")
    def test_observation_includes_mentions(self, predict_mock) -> None:
        predict_mock.return_value = {
            "confidence": 0.82, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        observation = predict_mock.call_args[0][0]
        self.assertIn("mentions", observation)
        self.assertGreaterEqual(observation["mentions"], 1)
        self.assertEqual(observation["description"].count("Early research prototype"), 1)

    @patch("pipeline.services._predict")
    def test_api_source_includes_title_and_role(self, predict_mock) -> None:
        predict_mock.return_value = {
            "confidence": 0.82, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        response = APIClient().get(f"/api/searches/{self.run.id}/")
        self.assertEqual(response.status_code, 200)
        source = response.data["candidates"][0]["sources"][0]
        self.assertTrue(source["title"])
        self.assertEqual(source["role"], "core")

    @patch("pipeline.services._predict")
    def test_crowded_topic_sends_higher_mentions_than_unique(self, predict_mock) -> None:
        self.run.documents.all().delete()
        abstract = "We report an experimental prototype of a laboratory quantum sensor device with readout electronics."
        crowded = (
            "Laboratory nv-center quantum sensor prototype alpha",
            "Portable nv-center quantum sensor prototype bravo",
            "Chip-scale nv-center quantum sensor prototype charlie",
        )
        unique = "Muonium spectroscopy quantum sensor prototype for axion searches"
        for index, title in enumerate((*crowded, unique)):
            SourceDocument.objects.create(
                run=self.run,
                provider="arxiv",
                external_id=f"http://arxiv.org/abs/2603.2000{index}",
                title=title,
                abstract=abstract,
                url=f"http://arxiv.org/abs/2603.2000{index}",
                published_date=date(2026, 3, 1),
                source_name="arXiv",
                source_type="preprint",
                language="en",
                trust=0.85,
            )
        predict_mock.return_value = {
            "confidence": 0.9, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        mentions_by_title = {
            call.args[0]["title"]: call.args[0]["mentions"]
            for call in predict_mock.call_args_list
        }
        self.assertGreater(mentions_by_title[crowded[0]], mentions_by_title[unique])

    @patch("pipeline.services._predict")
    def test_skips_commercially_mature_observation(self, predict_mock) -> None:
        predict_mock.return_value = {
            "confidence": 0.9,
            "weak_signal": True,
            "explanation": "зрелый",
            "factors": [
                {"name": "maturity_ratio", "value": 0.05, "direction": -1, "description": "зрелость"},
                {"name": "emergence_ratio", "value": 0.0, "direction": 1, "description": "зарождение"},
            ],
        }
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)

    @patch("pipeline.services._predict")
    def test_russian_phrase_dictionary_finds_english_project(self, predict_mock) -> None:
        self.run.query = "нейроморфные процессоры"
        self.run.save(update_fields=["query"])
        self.run.documents.all().delete()
        title = "A neuromorphic processor with on-chip spike learning"
        abstract = "We present an experimental neuromorphic processor prototype with on-chip learning and readout."
        SourceDocument.objects.create(
            run=self.run,
            provider="arxiv",
            external_id="http://arxiv.org/abs/2604.00001",
            title=title,
            abstract=abstract,
            url="http://arxiv.org/abs/2604.00001",
            published_date=date(2026, 4, 1),
            source_name="arXiv",
            source_type="preprint",
            language="en",
            trust=0.85,
        )
        predict_mock.return_value = {
            "confidence": 0.84, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.get().title, title)

    @patch("pipeline.services._predict")
    def test_rejects_ai_review_and_instrument_use(self, predict_mock) -> None:
        self.run.query = "Искусственный интеллект"
        self.run.save(update_fields=["query"])
        self.run.documents.all().delete()
        SourceDocument.objects.create(
            run=self.run,
            provider="arxiv",
            external_id="http://arxiv.org/abs/2604.10000",
            title="Revolutionizing healthcare: the role of artificial intelligence in clinical practice",
            abstract="We report an experimental laboratory setup and discuss possible applications in the field.",
            url="http://arxiv.org/abs/2604.10000",
            published_date=date(2026, 4, 1),
            source_name="arXiv",
            source_type="preprint",
            language="en",
            trust=0.85,
        )
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)

        self.run.query = "квантовые сенсоры"
        self.run.save(update_fields=["query"])
        self.run.documents.all().delete()
        SourceDocument.objects.create(
            run=self.run,
            provider="arxiv",
            external_id="http://arxiv.org/abs/2604.10001",
            title="Studying phonon coherence with a quantum sensor",
            abstract="We report an experimental laboratory setup and discuss possible applications in the field.",
            url="http://arxiv.org/abs/2604.10001",
            published_date=date(2026, 4, 1),
            source_name="arXiv",
            source_type="preprint",
            language="en",
            trust=0.85,
        )
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)
        predict_mock.assert_not_called()

    @patch("pipeline.services._predict")
    def test_empty_after_many_sources_is_honest_error(self, predict_mock) -> None:
        self.run.documents.all().delete()
        abstract = "A generic overview of the field without a device or prototype description at all."
        for index in range(20):
            SourceDocument.objects.create(
                run=self.run,
                provider="openalex",
                external_id=f"https://doi.org/10.1000/noise-{index}",
                title=f"List of quantum sensors volume {index}",
                abstract=abstract,
                url=f"https://doi.org/10.1000/noise-{index}",
                published_date=date(2026, 1, 1),
                source_name="OpenAlex",
                source_type="academic",
                language="en",
                trust=0.9,
            )
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)
        self.assertTrue(any("no_projects_after_filters" in error for error in self.run.errors))
        predict_mock.assert_not_called()

    @patch("pipeline.services._predict")
    def test_high_confidence_is_capped(self, predict_mock) -> None:
        self.run.documents.all().delete()
        abstract = "We report an experimental prototype of a laboratory quantum sensor device with readout electronics."
        for index in range(8):
            SourceDocument.objects.create(
                run=self.run,
                provider="arxiv",
                external_id=f"http://arxiv.org/abs/2605.1000{index}",
                title=f"Laboratory quantum sensor prototype {index} unique-token-{index}",
                abstract=abstract,
                url=f"http://arxiv.org/abs/2605.1000{index}",
                published_date=date(2026, 5, 1),
                source_name="arXiv",
                source_type="preprint",
                language="en",
                trust=0.85,
            )
        predict_mock.return_value = {
            "confidence": 0.9, "weak_signal": True, "explanation": "объяснение", "factors": [],
        }
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 8)
        self.assertLessEqual(self.run.high_confidence_count, 4)
        self.assertEqual(self.run.high_confidence_count, 2)

    @patch("pipeline.services._predict")
    def test_untranslated_query_records_error(self, predict_mock) -> None:
        self.run.query = "топологические изоляторы"
        self.run.save(update_fields=["query"])
        self.run.documents.all().delete()
        finalize_search.run([], str(self.run.id))
        self.assertEqual(self.run.candidates.count(), 0)
        self.assertTrue(any("query_not_translated" in error for error in self.run.errors))
        predict_mock.assert_not_called()
