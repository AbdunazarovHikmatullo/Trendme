"""ML-сервис: обучение, инференс и интерпретация классификации слабых сигналов.

Поиск, агрегация источников и оркестрация намеренно остаются в Django-сервисе.
"""

from fastapi import FastAPI

from core.config import settings
from core.model import WeakSignalModel
from core.schemas import (
    ModelInfo,
    PredictRequest,
    PredictResponse,
    PredictionOut,
    TrainRequest,
    TrainResponse,
)

model = WeakSignalModel()
if settings.model_path.exists():
    model.load(settings.model_path)

app = FastAPI(title="TrendMe ML Service")


@app.get("/")
def root() -> dict:
    return {"service": "trendme-ml", "status": "ok", "model_trained": model.trained}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@app.get("/model", response_model=ModelInfo)
def model_info() -> ModelInfo:
    return ModelInfo(
        trained=model.trained,
        threshold=model.threshold,
        high_confidence_threshold=settings.high_confidence_threshold,
        features=list(model.extractor.NUMERIC_FEATURES),
        directions=model.feature_directions,
        importances=model.feature_importances,
        coefficients=model.coefficients,
        intercept=model.intercept,
    )


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    observations = [obs.model_dump() for obs in request.observations]
    predictions = model.predict(observations, top_n=request.top_n)

    weak_signals = sum(1 for p in predictions if p.weak_signal)
    high_confidence = sum(
        1 for p in predictions if p.confidence >= settings.high_confidence_threshold
    )

    return PredictResponse(
        query=request.query,
        threshold=model.threshold,
        high_confidence_threshold=settings.high_confidence_threshold,
        total=len(predictions),
        weak_signals=weak_signals,
        high_confidence=high_confidence,
        predictions=[
            PredictionOut(
                weak_signal=p.weak_signal,
                confidence=p.confidence,
                factors=[
                    {
                        "name": f.name,
                        "value": f.value,
                        "direction": f.direction,
                        "description": f.description,
                        "weight": f.weight,
                        "contribution": f.contribution,
                    }
                    for f in p.factors
                ],
                explanation=p.explanation,
                signal_strength=p.signal_strength,
            )
            for p in predictions
        ],
    )


@app.post("/train", response_model=TrainResponse)
def train(request: TrainRequest) -> TrainResponse:
    observations = [obs.model_dump() for obs in request.observations]
    metrics = model.fit(observations, request.labels)
    model_path = model.save()
    return TrainResponse(metrics=metrics, model_path=model_path, trained=model.trained)
