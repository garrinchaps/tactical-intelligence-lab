from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from src.machine_learning.evaluation import binary_metrics, evaluate_temporal, temporal_split
from src.machine_learning.model_catalog import model_cards


def _frame():
    rows = []
    for i in range(20):
        rows.append({"date": f"2026-01-{i + 1:02d}", "match_id": i, "x": float(i % 4), "target": i % 2})
    return pd.DataFrame(rows)


def test_temporal_split_never_mixes_groups():
    frame = _frame()
    train, test, cutoff = temporal_split(frame, date_column="date", group_column="match_id", test_fraction=0.25)
    assert train.sum() > test.sum() and cutoff == "2026-01-15"
    assert set(frame.loc[train, "match_id"]).isdisjoint(frame.loc[test, "match_id"])


def test_temporal_evaluation_reports_model_and_baseline():
    frame = _frame()
    result = evaluate_temporal(
        frame,
        feature_columns=["x"],
        target_column="target",
        date_column="date",
        group_column="match_id",
        model_factory=lambda: LogisticRegression(),
    )
    assert result["split"]["strategy"] == "temporal"
    assert "roc_auc" in result["model"]
    assert "brier" in result["baseline_majority"]


def test_binary_metrics_contains_confusion_matrix():
    result = binary_metrics([0, 1, 1, 0], [0.1, 0.9, 0.7, 0.2])
    assert result["accuracy"] == 1.0
    assert result["confusion_matrix"] == [[2, 0], [0, 2]]


def test_model_cards_are_honest_and_serializable():
    cards = model_cards()
    assert len(cards) >= 5
    assert all(card["id"] and card["status"] and card["limitations"] for card in cards)
    assert any(card["status"] == "implementado-experimental" for card in cards)


def test_temporal_split_rejects_invalid_dates():
    with pytest.raises(ValueError):
        temporal_split(pd.DataFrame({"date": ["x"], "match_id": [1]}), date_column="date", group_column="match_id")
