"""Pydantic-схемы API ML-сервиса."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: Optional[str] = None
    url: Optional[str] = None
    date: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    trust: Optional[float] = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    text: Optional[str] = None
    summary: Optional[str] = None
    published_date: Optional[str] = None
    date: Optional[str] = None
    first_seen: Optional[str] = None
    source_type: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    language: Optional[str] = None
    source_trust: Optional[float] = None
    mentions: Optional[int] = None
    frequency: Optional[int] = None
    occurrences: Optional[int] = None
    mentions_series: Optional[List[float]] = None
    has_patent: Optional[bool] = None
    patent: Optional[bool] = None
    patents: Optional[int] = None
    patent_count: Optional[int] = None
    has_investment: Optional[bool] = None
    investment: Optional[bool] = None
    investments: Optional[int] = None
    funding: Optional[bool] = None
    investment_amount: Optional[float] = None
    source: Optional[SourceIn] = None
    label: Optional[bool] = None


class FactorOut(BaseModel):
    name: str
    value: float
    direction: int
    description: str
    weight: float = 0.0
    contribution: float = 0.0


class PredictionOut(BaseModel):
    weak_signal: bool
    confidence: float
    factors: List[FactorOut]
    explanation: str
    signal_strength: Optional[float] = None


class PredictRequest(BaseModel):
    query: Optional[str] = None
    observations: List[Observation]
    top_n: int = Field(default=15, ge=1, le=100)


class PredictResponse(BaseModel):
    query: Optional[str] = None
    threshold: float
    high_confidence_threshold: float
    total: int
    weak_signals: int
    high_confidence: int
    predictions: List[PredictionOut]


class TrainRequest(BaseModel):
    observations: List[Observation]
    labels: List[int]

    @model_validator(mode="after")
    def validate_training_data(self) -> "TrainRequest":
        if len(self.observations) != len(self.labels):
            raise ValueError("Число observations должно совпадать с числом labels.")
        if len(self.observations) < 4:
            raise ValueError("Для обучения нужны минимум 4 наблюдения.")
        if set(self.labels) != {0, 1}:
            raise ValueError("labels должны содержать оба класса: 0 и 1.")
        if min(self.labels.count(0), self.labels.count(1)) < 2:
            raise ValueError("В каждом классе для обучения нужно минимум 2 наблюдения.")
        return self


class TrainResponse(BaseModel):
    metrics: Dict[str, Any]
    model_path: str
    trained: bool


class ModelInfo(BaseModel):
    trained: bool
    threshold: float
    high_confidence_threshold: float
    features: List[str]
    directions: Dict[str, int]
    importances: Dict[str, float]
    coefficients: Dict[str, float]
    intercept: float
