"""
Testes Automatizados do Dia 7: Validação do Treinamento Supervisionado (XGBoost + Baseline),
Separação por Partida (GroupShuffleSplit), Brier Score e Persistência com Joblib.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from src.machine_learning.supervised import PossessionDangerClassifier


def test_xgboost_training_group_split_and_persistence(tmp_path: Path):
    """
    Gera 120 cadeias de posse distribuídas em 4 partidas distintas (match_id 1 a 4)
    com padrão físico claro (posses rápidas e com ações progressivas geram perigo)
    e verifica se o modelo aprende (ROC-AUC > 0.75, Brier Score < 0.25) e persiste no disco.
    """
    rng = np.random.default_rng(42)
    rows = []

    for i in range(120):
        match_id = (i % 4) + 1
        is_dangerous = 1 if (i % 3 == 0) else 0

        x_start = float(rng.uniform(55.0, 78.0) if is_dangerous else rng.uniform(15.0, 50.0))
        y_start = float(rng.uniform(20.0, 60.0))
        prog_actions = int(rng.integers(2, 5) if is_dangerous else rng.integers(0, 2))
        speed = float(rng.uniform(2.5, 5.5) if is_dangerous else rng.uniform(0.2, 1.8))

        rows.append(
            {
                "match_id": match_id,
                "period": 1,
                "possession_id": i + 1,
                "team_name": "Equipe IA",
                "start_third": "Terço Médio" if x_start >= 40 else "Terço Defensivo",
                "start_corridor": "Corredor Central",
                "x_start": x_start,
                "y_start": y_start,
                "x_end": 105.0 if is_dangerous else 45.0,
                "y_end": 40.0,
                "duration_sec": 8.0,
                "num_events": 8,
                "num_passes": 5,
                "completed_passes": 5 if is_dangerous else 3,
                "progressive_actions": prog_actions,
                "net_progression_m": 35.0 if is_dangerous else 5.0,
                "direct_speed_m_s": speed,
                "entered_zone_14": is_dangerous,
                "entered_box": is_dangerous,
                "is_counter_attack": is_dangerous,
                "ended_in_shot": is_dangerous,
                "chain_xg": 0.15 if is_dangerous else 0.0,
                "under_pressure_ratio": 0.2,
            }
        )

    df_chains = pd.DataFrame(rows)

    clf = PossessionDangerClassifier(
        model_dir=str(tmp_path / "trained"),
        eval_dir=str(tmp_path / "eval"),
    )
    metrics = clf.train_and_evaluate(df_chains, test_size=0.25, random_state=42)

    assert "GroupShuffleSplit" in metrics["split_strategy"]
    assert metrics["xgboost_metrics"]["test_roc_auc"] > 0.75
    assert metrics["xgboost_metrics"]["test_brier_score"] < 0.25

    # Testa carregamento do disco em uma nova instância
    clf_loaded = PossessionDangerClassifier(
        model_dir=str(tmp_path / "trained"),
        eval_dir=str(tmp_path / "eval"),
    )
    assert clf_loaded.load_models() is True

    pred_res = clf_loaded.predict_possession_probabilities(
        df_chains, target_team="Equipe IA"
    )
    assert pred_res["status"] == "OK"
    assert pred_res["total_possessions_scored"] == 120
    assert len(pred_res["top_3_most_dangerous_possessions"]) == 3