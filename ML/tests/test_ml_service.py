"""Регрессионные проверки ML-ядра и контрактов FastAPI."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from core.dataset import _latest_year
from core.model import WeakSignalModel
from main import health, predict, train
from core.schemas import Observation, PredictRequest, TrainRequest


class DatasetTests(unittest.TestCase):
    def test_latest_year_keeps_full_year(self) -> None:
        self.assertEqual(_latest_year("https://example.org/report-2026"), 2026)


class ModelTests(unittest.TestCase):
    def test_rejects_singleton_class(self) -> None:
        observations = [{"title": str(index)} for index in range(4)]
        with self.assertRaises(ValueError):
            WeakSignalModel().fit(observations, [0, 0, 0, 1])

    def test_rule_based_prediction_explains_factors(self) -> None:
        prediction = WeakSignalModel().predict([{
            "title": "Лабораторный прототип квантового сенсора",
            "description": "Раннее научное исследование и пилот",
            "source_type": "academic",
            "published_date": "2026-01-01",
            "mentions": 2,
            "has_patent": True,
        }])[0]
        self.assertGreater(prediction.confidence, 0.5)
        self.assertTrue(prediction.factors)
        self.assertNotEqual(prediction.explanation, "выраженные признаки не обнаружены.")


class ServiceTests(unittest.TestCase):
    def test_health(self) -> None:
        self.assertEqual(health(), {"status": "healthy"})

    def test_predict_returns_interpretation(self) -> None:
        response = predict(PredictRequest(
            query="квантовые технологии",
            observations=[Observation(
                title="Лабораторный прототип квантового сенсора",
                description="Ранний пилот и научное исследование",
                source_type="academic",
                published_date="2026-01-01",
                mentions=3,
                has_patent=True,
            )],
        ))
        self.assertEqual(response.total, 1)
        self.assertTrue(response.predictions[0].factors)

    def test_invalid_top_n_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            PredictRequest(observations=[], top_n=0)

    def test_train_rejects_invalid_labels(self) -> None:
        with self.assertRaises(ValidationError):
            TrainRequest(observations=[Observation(title="a")] * 4, labels=[0, 0, 0, 1])

    def test_train_accepts_minimal_stratified_dataset(self) -> None:
        response = train(TrainRequest(
            observations=[
                Observation(title="Зрелая технология", description="массово внедренный стандарт", mentions=5000),
                Observation(title="Зрелый рынок", description="широко используемая коммерческая система", mentions=3000),
                Observation(title="Ранний прототип", description="лабораторный пилот", source_type="academic", mentions=2),
                Observation(title="Научная гипотеза", description="экспериментальное исследование", source_type="academic", mentions=1),
            ],
            labels=[0, 0, 1, 1],
        ))
        self.assertTrue(response.trained)


if __name__ == "__main__":
    unittest.main()
