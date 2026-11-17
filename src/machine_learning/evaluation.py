"""Avaliação reprodutível de modelos com separação temporal e por entidade."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)


def temporal_split(
    frame: pd.DataFrame,
    *,
    date_column: str,
    group_column: str,
    test_fraction: float = 0.25,
) -> tuple[np.ndarray, np.ndarray, str]:
    """Divide por datas inteiras, mantendo grupos inteiros fora do teste.

    A data do teste é sempre posterior à última data do treino. Isso evita que
    uma linha futura influencie treinamento, normalização ou seleção de modelo.
    """
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction deve estar entre 0 e 1")
    if date_column not in frame or group_column not in frame:
        raise KeyError(f"colunas obrigatórias ausentes: {date_column}, {group_column}")
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    if dates.isna().any():
        raise ValueError("a coluna temporal contém datas inválidas")
    unique_dates = np.array(sorted(dates.dt.normalize().unique()))
    if len(unique_dates) < 2:
        raise ValueError("são necessárias pelo menos duas datas distintas")
    cutoff_index = max(1, int(np.ceil(len(unique_dates) * (1 - test_fraction))) - 1)
    cutoff = unique_dates[cutoff_index]
    train = dates.dt.normalize().to_numpy() <= cutoff
    test = ~train
    if not train.any() or not test.any():
        raise ValueError("split temporal não produziu treino e teste")
    train_groups = set(frame.loc[train, group_column])
    test_groups = set(frame.loc[test, group_column])
    if train_groups & test_groups:
        raise ValueError("data leakage: o mesmo grupo aparece no treino e no teste")
    return train, test, pd.Timestamp(cutoff).date().isoformat()


def binary_metrics(y_true: Any, probabilities: Any, threshold: float = 0.5) -> dict[str, Any]:
    """Métricas de classificação e matriz de confusão para um conjunto fixo."""
    y = np.asarray(y_true, dtype=int)
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    predicted = (p >= threshold).astype(int)
    result: dict[str, Any] = {
        "accuracy": round(float(accuracy_score(y, predicted)), 6),
        "precision": round(float(precision_score(y, predicted, zero_division=0)), 6),
        "recall": round(float(recall_score(y, predicted, zero_division=0)), 6),
        "f1": round(float(f1_score(y, predicted, zero_division=0)), 6),
        "brier": round(float(brier_score_loss(y, p)), 6),
        "log_loss": round(float(log_loss(y, p, labels=[0, 1])), 6),
        "confusion_matrix": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
    }
    result["roc_auc"] = round(float(roc_auc_score(y, p)), 6) if len(np.unique(y)) == 2 else None
    return result


def evaluate_temporal(
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
    target_column: str,
    date_column: str,
    group_column: str,
    model_factory: Callable[[], Any],
    test_fraction: float = 0.25,
) -> dict[str, Any]:
    """Treina um modelo apenas no passado e compara com baseline majoritário."""
    train_mask, test_mask, cutoff = temporal_split(
        frame, date_column=date_column, group_column=group_column, test_fraction=test_fraction
    )
    clean = frame.dropna(subset=feature_columns + [target_column]).reset_index(drop=True)
    # Recalcula as máscaras após o drop para manter alinhamento por índice original.
    train_mask, test_mask, cutoff = temporal_split(
        clean, date_column=date_column, group_column=group_column, test_fraction=test_fraction
    )
    X_train = clean.loc[train_mask, feature_columns]
    X_test = clean.loc[test_mask, feature_columns]
    y_train = clean.loc[train_mask, target_column].astype(int)
    y_test = clean.loc[test_mask, target_column].astype(int)
    if y_train.nunique() < 2 or y_test.nunique() < 2:
        raise ValueError("treino e teste precisam conter as duas classes")
    model = model_factory()
    model.fit(X_train, y_train)
    probability = model.predict_proba(X_test)[:, 1]
    majority = np.full(len(y_test), float(y_train.mean()))
    return {
        "split": {
            "strategy": "temporal",
            "cutoff": cutoff,
            "train_rows": int(len(y_train)),
            "test_rows": int(len(y_test)),
            "train_groups": int(clean.loc[train_mask, group_column].nunique()),
            "test_groups": int(clean.loc[test_mask, group_column].nunique()),
        },
        "model": binary_metrics(y_test, probability),
        "baseline_majority": binary_metrics(y_test, majority),
    }
