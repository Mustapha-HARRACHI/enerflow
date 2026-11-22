"""Causal next-day regional electricity-demand forecasting on RTE Gold data."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import json

import duckdb
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_NAMES = (
    "lag_1", "lag_2", "lag_7", "lag_14", "mean_7", "mean_14",
    "dow_sin", "dow_cos", "month_sin", "month_cos",
    "region_bretagne", "region_hauts_de_france", "region_occitanie",
)
REGIONS = ("Bretagne", "Hauts-de-France", "Occitanie")
CONFIG = json.loads(Path("config/experiment.json").read_text(encoding="utf-8"))
TRAIN_END = date.fromisoformat(CONFIG["train_end"])
VALID_END = date.fromisoformat(CONFIG["validation_end"])
TEST_END = date.fromisoformat(CONFIG["test_end"])


def load_daily(path: Path) -> dict[str, list[tuple[date, float]]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing Gold dataset: {path}; run src/03_build_gold.py")
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT libelle_region, date_utc, consommation_estimee_mwh, nb_intervalles "
            "FROM read_parquet(?) ORDER BY libelle_region, date_utc", [str(path)]
        ).fetchall()
    finally:
        con.close()
    grouped: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for region, day, value, intervals in rows:
        if region not in REGIONS or intervals != 48 or value is None or value <= 0:
            raise ValueError(f"Invalid daily observation: {region}, {day}, {value}, {intervals}")
        grouped[region].append((day, float(value)))
    if set(grouped) != set(REGIONS):
        raise ValueError(f"Expected regions {REGIONS}; found {tuple(grouped)}")
    for region, series in grouped.items():
        if len(series) != 181 or series[0][0] != date(2025, 1, 1) or series[-1][0] != TEST_END:
            raise ValueError(f"Unexpected coverage for {region}: {len(series)} days")
        if any(series[i][0] - series[i-1][0] != timedelta(days=1) for i in range(1, len(series))):
            raise ValueError(f"Missing or duplicate day in {region}")
    return dict(grouped)


def feature_for_day(region: str, day: date, history: list[float]) -> np.ndarray:
    """The target day is absent from history; all lag features are observed earlier."""
    if region not in REGIONS or len(history) < 14:
        raise ValueError("Unknown region or fewer than 14 prior days")
    dow = day.weekday()
    month = day.month
    return np.array([
        history[-1], history[-2], history[-7], history[-14],
        float(np.mean(history[-7:])), float(np.mean(history[-14:])),
        np.sin(2*np.pi*dow/7), np.cos(2*np.pi*dow/7),
        np.sin(2*np.pi*month/12), np.cos(2*np.pi*month/12),
        *[float(region == candidate) for candidate in REGIONS],
    ], dtype=float)


def make_rows(grouped: dict[str, list[tuple[date, float]]]) -> list[dict]:
    rows = []
    for region in REGIONS:
        series = grouped[region]
        values = [value for _, value in series]
        for i in range(14, len(series)):
            day, actual = series[i]
            features = feature_for_day(region, day, values[:i])
            rows.append({"region": region, "date": day, "actual_mwh": actual,
                         "baseline_mwh": values[i-7], "features": features})
    return rows


def partition(rows: list[dict], name: str) -> list[dict]:
    if name == "train":
        return [r for r in rows if r["date"] <= TRAIN_END]
    if name == "validation":
        return [r for r in rows if TRAIN_END < r["date"] <= VALID_END]
    if name == "test":
        return [r for r in rows if VALID_END < r["date"] <= TEST_END]
    raise ValueError(name)


def fit_model(rows: list[dict], alpha: float):
    x = np.stack([r["features"] for r in rows])
    y = np.array([r["actual_mwh"] for r in rows])
    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    model.fit(x, y)
    return model


def predict(model, rows: list[dict]) -> np.ndarray:
    return np.maximum(0, model.predict(np.stack([r["features"] for r in rows])))


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    errors = actual - predicted
    return {"mae_mwh": float(np.mean(np.abs(errors))),
            "rmse_mwh": float(np.sqrt(np.mean(errors ** 2))),
            "wape_pct": float(100 * np.sum(np.abs(errors)) / np.sum(actual))}
