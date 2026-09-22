"""Оценка уровня сигнала: интерпретируемая логистическая регрессия над факторами."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split

from .config import settings
from .features import NEUTRAL_VALUES, Factor, FeatureExtractor, normalize_observation
from .signals import PRIOR_DIRECTIONS


@dataclass
class Prediction:
    weak_signal: bool
    confidence: float
    factors: List[Factor]
    explanation: str
    signal_strength: float | None = None


class WeakSignalModel:
    def __init__(
        self,
        threshold: float | None = None,
        random_state: int | None = None,
        regularization: float = 1.0,
    ) -> None:
        self.threshold = threshold or settings.weak_signal_threshold
        self.random_state = random_state or settings.random_state
        self.regularization = regularization
        self.extractor = FeatureExtractor()
        self.feature_names = list(FeatureExtractor.NUMERIC_FEATURES)
        self.model = LogisticRegression(
            C=self.regularization,
            class_weight="balanced",
            max_iter=2000,
            random_state=self.random_state,
        )
        self.trained = False
        self.feature_directions: Dict[str, int] = dict(PRIOR_DIRECTIONS)
        self.coefficients: Dict[str, float] = {}
        self.intercept: float = 0.0
        self.feature_importances: Dict[str, float] = {}
        self.strength_model = None
        self.strength_trained = False

    def _matrix(self, norm_obs: List[Dict[str, Any]]) -> np.ndarray:
        rows = []
        for obs in norm_obs:
            features = self.extractor.extract_features(obs)
            rows.append([features[name] for name in self.feature_names])
        return np.array(rows, dtype=float)

    def fit(self, observations: List[Any], labels: List[int]) -> Dict[str, float]:
        if len(observations) != len(labels):
            raise ValueError("Число наблюдений должно совпадать с числом меток.")
        if len(observations) < 4 or set(labels) != {0, 1}:
            raise ValueError("Для обучения нужны минимум 4 наблюдения двух классов (0 и 1).")
        if min(labels.count(0), labels.count(1)) < 2:
            raise ValueError("В каждом классе для обучения нужно минимум 2 наблюдения.")
        norm_obs = [normalize_observation(o) for o in observations]
        X = self._matrix(norm_obs)
        y = np.asarray(labels, dtype=int)

        stratify = y if len(set(y)) > 1 else None
        # При маленькой демонстрационной выборке доля 20% может дать только одно
        # наблюдение и сломать стратификацию. Оставляем минимум по одному объекту
        # каждого класса в тестовой и обучающей частях.
        test_count = max(2, math.ceil(len(X) * settings.test_size))
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_count, stratify=stratify, random_state=self.random_state
        )

        self.model.fit(X_train, y_train)
        self.trained = True
        self._extract_coefficients()

        pred = self.model.predict(X_test)
        return {
            "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, pred, zero_division=0)), 4),
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
        }

    def _extract_coefficients(self) -> None:
        coef = self.model.coef_[0]
        self.intercept = float(self.model.intercept_[0])
        self.coefficients = {
            name: float(coef[i]) for i, name in enumerate(self.feature_names)
        }
        for name, weight in self.coefficients.items():
            if abs(weight) > 1e-3:
                self.feature_directions[name] = 1 if weight > 0 else -1
        total = sum(abs(w) for w in self.coefficients.values()) or 1.0
        self.feature_importances = {
            name: round(abs(w) / total, 4) for name, w in self.coefficients.items()
        }

    def calibrate_strength(self, observations: List[Any], bally: List[Any], alpha: float = 1.0) -> Dict[str, float]:
        valid = [
            (o, b) for o, b in zip(observations, bally)
            if b is not None and not (isinstance(b, float) and math.isnan(b))
        ]
        if not valid:
            self.strength_trained = False
            return {"correlation": 0.0, "mae": 0.0}
        obs, y = zip(*valid)
        X = self._matrix([normalize_observation(o) for o in obs])
        y = np.asarray(y, dtype=float)
        self.strength_model = Ridge(alpha=alpha, random_state=self.random_state)
        self.strength_model.fit(X, y)
        self.strength_trained = True
        pred = self.strength_model.predict(X)
        corr = float(np.corrcoef(pred, y)[0, 1]) if len(y) > 1 else 0.0
        mae = float(np.mean(np.abs(pred - y)))
        return {"correlation": round(corr, 4), "mae": round(mae, 4)}

    def _signal_strength(self, obs: Dict[str, Any]) -> float:
        if not self.strength_trained:
            return 0.0
        X = self._matrix([obs])
        raw = float(self.strength_model.predict(X)[0])
        return round(max(0.0, min(1.0, (raw - 3.0) / 4.0)), 4)

    def cross_validate(self, observations: List[Any], labels: List[int], cv: int = 5) -> Dict[str, float]:
        norm_obs = [normalize_observation(o) for o in observations]
        X = self._matrix(norm_obs)
        y = np.asarray(labels, dtype=int)
        class_counts = np.bincount(y)
        nonzero_counts = class_counts[class_counts > 0]
        if len(nonzero_counts) < 2:
            raise ValueError("Для кросс-валидации нужны наблюдения двух классов.")
        folds = min(cv, int(nonzero_counts.min()))
        if folds < 2:
            raise ValueError("Для кросс-валидации в каждом классе нужно минимум 2 наблюдения.")
        results = cross_validate(
            self.model,
            X,
            y,
            cv=StratifiedKFold(n_splits=folds, shuffle=True, random_state=self.random_state),
            scoring=["accuracy", "precision", "recall", "f1"],
        )
        return {key: round(float(np.mean(results[f"test_{key}"])), 4) for key in ("accuracy", "precision", "recall", "f1")}

    def _rule_score(self, obs: Dict[str, Any]) -> float:
        features = self.extractor.extract_features(obs)
        contribution = 0.0
        for name in self.feature_names:
            direction = self.feature_directions.get(name, PRIOR_DIRECTIONS.get(name, 0))
            contribution += direction * (features[name] - NEUTRAL_VALUES[name])
        return 1.0 / (1.0 + math.exp(-contribution))

    def explain(self, obs: Dict[str, Any]) -> List[Factor]:
        factors = self.extractor.extract_factors(obs, self.feature_directions)
        for factor in factors:
            weight = self.coefficients.get(factor.name, 0.0) if self.trained else float(factor.direction)
            factor.weight = round(weight, 4)
            factor.contribution = round(weight * (factor.value - NEUTRAL_VALUES[factor.name]), 4)
        factors.sort(key=lambda f: -abs(f.contribution))
        return factors

    def _explanation_ru(self, factors: List[Factor]) -> str:
        meaningful = [f for f in factors if abs(f.contribution) > 0.01]
        positive = [f for f in meaningful[:4] if f.contribution > 0]
        negative = [f for f in meaningful[:4] if f.contribution < 0]
        chunks: List[str] = []
        if positive:
            chunks.append(
                "в пользу слабого сигнала: "
                + ", ".join(f"{f.description.lower()} ({f.value:.2f})" for f in positive)
            )
        if negative:
            chunks.append(
                "против (зрелость/шум): "
                + ", ".join(f"{f.description.lower()} ({f.value:.2f})" for f in negative)
            )
        if not chunks:
            chunks.append("выраженные признаки не обнаружены")
        return ". ".join(chunks) + "."

    def predict(self, observations: List[Any], top_n: int | None = None) -> List[Prediction]:
        norm_obs = [normalize_observation(o) for o in observations]
        if self.trained:
            X = self._matrix(norm_obs)
            proba = self.model.predict_proba(X)[:, 1]
        else:
            proba = np.array([self._rule_score(o) for o in norm_obs])

        results = []
        for obs, prob in zip(norm_obs, proba):
            confidence = float(prob)
            factors = self.explain(obs)
            results.append(
                Prediction(
                    weak_signal=confidence >= self.threshold,
                    confidence=round(confidence, 4),
                    factors=factors,
                    explanation=self._explanation_ru(factors),
                    signal_strength=self._signal_strength(obs) if self.strength_trained else None,
                )
            )

        results.sort(key=lambda r: r.confidence, reverse=True)
        if top_n is not None:
            results = results[:top_n]
        return results

    def save(self, path: Any = None) -> str:
        path = Path(path or settings.model_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "coefficients": self.coefficients,
                "intercept": self.intercept,
                "feature_directions": self.feature_directions,
                "feature_importances": self.feature_importances,
                "feature_names": self.feature_names,
                "threshold": self.threshold,
                "trained": self.trained,
                "strength_model": self.strength_model,
                "strength_trained": self.strength_trained,
            },
            path,
        )
        return str(path)

    def load(self, path: Any = None) -> None:
        data = joblib.load(path or settings.model_path)
        self.model = data["model"]
        self.coefficients = data["coefficients"]
        self.intercept = data["intercept"]
        self.feature_directions = data["feature_directions"]
        self.feature_importances = data["feature_importances"]
        self.feature_names = data["feature_names"]
        self.threshold = data["threshold"]
        self.trained = data["trained"]
        self.strength_model = data.get("strength_model")
        self.strength_trained = data.get("strength_trained", False)
