"""Конфигурация ML-сервиса."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    artifact_dir: Path = Path(__file__).resolve().parent.parent / "artifacts"
    model_filename: str = "weak_signal_model.joblib"
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    weak_signals_filename: str = "100_слабых_технологических_сигналов_сентябрь_2026.xlsx"
    mature_filename: str = "mature_technologies.csv"
    weak_signal_threshold: float = 0.5
    high_confidence_threshold: float = 0.75
    random_state: int = 42
    test_size: float = 0.2

    @property
    def model_path(self) -> Path:
        return self.artifact_dir / self.model_filename

    @property
    def weak_signals_path(self) -> Path:
        return self.data_dir / self.weak_signals_filename

    @property
    def mature_path(self) -> Path:
        return self.data_dir / self.mature_filename


settings = Settings()
