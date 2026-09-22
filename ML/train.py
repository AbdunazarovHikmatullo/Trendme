"""CLI-скрипт обучения и оценки модели «слабый сигнал vs зрелый тренд».

Пример:
    python train.py --weak data/....xlsx --mature data/mature_technologies.csv --save
"""

import argparse
import json
from pathlib import Path

from core.config import settings
from core.dataset import load_dataset
from core.model import WeakSignalModel


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучить модель слабых сигналов")
    parser.add_argument("--weak", default=str(settings.weak_signals_path), help="xlsx со слабыми сигналами")
    parser.add_argument("--mature", default=str(settings.mature_path), help="csv со зрелыми технологиями")
    parser.add_argument("--save", action="store_true", help="Сохранить модель")
    parser.add_argument("--report", action="store_true", help="Сохранить отчёт об оценке")
    args = parser.parse_args()

    data = load_dataset(args.weak, args.mature)
    print(f"Датасет: {data['n_weak']} слабых + {data['n_mature']} зрелых = {len(data['observations'])}")

    model = WeakSignalModel()

    print("\nБинарная классификация — кросс-валидация (5-fold):")
    cv = model.cross_validate(data["observations"], data["labels"])
    for key, value in cv.items():
        print(f"  {key}: {value}")

    print("\nБинарная классификация — train/test split:")
    test_metrics = model.fit(data["observations"], data["labels"])
    for key, value in test_metrics.items():
        print(f"  {key}: {value}")

    print("\nКалибровка силы сигнала на «Балл» (Ridge, только слабые):")
    strength = model.calibrate_strength(data["observations"], data["bally"])
    for key, value in strength.items():
        print(f"  {key}: {value}")

    print("\nВеса (коэффициенты):")
    for name, weight in sorted(model.coefficients.items(), key=lambda kv: -abs(kv[1])):
        print(f"  {name:18s} {weight:+.3f}")

    if args.save:
        path = model.save()
        print(f"\nМодель сохранена: {path}")

    if args.report or args.save:
        report = {
            "dataset": {
                "n_weak": data["n_weak"],
                "n_mature": data["n_mature"],
                "n_total": len(data["observations"]),
            },
            "binary_cv": cv,
            "binary_test": test_metrics,
            "strength": strength,
            "threshold": model.threshold,
            "high_confidence_threshold": settings.high_confidence_threshold,
            "features": model.feature_names,
            "weights": model.coefficients,
            "directions": model.feature_directions,
        }
        report_path = Path(settings.artifact_dir) / "model_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Отчёт сохранён: {report_path}")


if __name__ == "__main__":
    main()
