"""Data-backed checks for split integrity and feature availability."""

from datetime import date
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from forecasting import feature_for_day, load_daily, make_rows, partition, metrics


def test_features_ignore_target_and_future():
    grouped = load_daily(Path("data/processed/gold/regional_daily.parquet"))
    before_rows = make_rows(grouped)
    original = next(r for r in before_rows if r["region"] == "Bretagne" and r["date"] == date(2025, 5, 1))
    grouped["Bretagne"] = [(d, v + 100000 if d == date(2025, 5, 1) else v) for d, v in grouped["Bretagne"]]
    after_rows = make_rows(grouped)
    changed = next(r for r in after_rows if r["region"] == "Bretagne" and r["date"] == date(2025, 5, 1))
    # The target changes, but features and baseline for that forecast remain fixed.
    assert original["actual_mwh"] != changed["actual_mwh"]
    assert original["baseline_mwh"] == changed["baseline_mwh"]
    np.testing.assert_array_equal(original["features"], changed["features"])
    history = list(range(1, 21))
    before = feature_for_day("Bretagne", date(2025, 5, 1), history)
    after = feature_for_day("Bretagne", date(2025, 5, 1), list(history))
    np.testing.assert_array_equal(before, after)
    assert before[0] == 20 and before[2] == 14 and before[3] == 7


def test_real_data_splits_and_weekly_reference():
    path = Path("data/processed/gold/regional_daily.parquet")
    if not path.exists():
        pytest.fail(f"Missing {path}; run the ingestion pipeline before tests")
    rows = make_rows(load_daily(path))
    train, valid, test = (partition(rows, name) for name in ("train", "validation", "test"))
    assert (len(train), len(valid), len(test)) == (318, 93, 90)
    assert len(train) + len(valid) + len(test) == len(rows)
    assert max(r["date"] for r in train) < min(r["date"] for r in valid)
    assert max(r["date"] for r in valid) < min(r["date"] for r in test)
    assert all(r["baseline_mwh"] > 0 for r in rows)
    assert metrics(np.array([r["actual_mwh"] for r in test]),
                   np.array([r["baseline_mwh"] for r in test]))["mae_mwh"] > 0


def test_unknown_region_fails():
    with pytest.raises(ValueError):
        feature_for_day("Unknown", date(2025, 6, 1), [1.0] * 14)
