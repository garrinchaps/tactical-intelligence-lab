"""Regressões da inteligência compartilhada: telemetria, feedback, fontes de dados e avaliação da escalação."""

import json

import pandas as pd


def test_questions_and_feedback_are_audited_not_used_as_training_labels(tmp_path):
    from src.intelligence.learning_hub import learning_summary, record_feedback, record_interaction

    interactions = tmp_path / "interactions.jsonl"
    feedback = tmp_path / "feedback.jsonl"
    result = {
        "scope": {"ask": "ranking", "category": "match"},
        "evidence": {"blocos": {"perigo::atacante": {}}, "metadata": {"data_source": "openplay"}},
        "hallucination_audit": {"is_grounded": True, "numbers_total": 3},
        "engine_used": "local",
        "latency_s": 0.7,
    }
    interaction_id = record_interaction(
        "Quem criou mais perigo?", result, {"match_id": 123, "data_level": "EVENTS"}, interactions
    )
    record_feedback(interaction_id, 0, "A resposta não considerou o segundo tempo.", feedback)

    row = json.loads(interactions.read_text(encoding="utf-8").strip())
    assert row["match_id"] == 123
    assert row["danger_model_evidence_present"] is True
    assert row["trained_from_this_question"] is False
    assert row["learning_status"] == "registrada_para_auditoria"

    summary = learning_summary(interactions, feedback)
    assert summary["questions_recorded"] == 1
    assert summary["negative_feedback"] == 1
    assert summary["feedback_pending_review"] == 1
    assert summary["questions_that_changed_weights"] == 0
    assert summary["feedback_that_changed_weights"] == 0


def test_danger_model_accepts_new_and_legacy_feature_shapes():
    import numpy as np

    from src.machine_learning.danger_dataset import FEATURES, LEGACY_FEATURES
    from src.machine_learning.model_registry import DangerModelRegistry
    from src.machine_learning.neural_net import NeuralNetwork

    assert len(FEATURES) == len(LEGACY_FEATURES) + 1
    assert FEATURES[-1] == "density_is_360"
    rows = pd.DataFrame({name: np.zeros(3) for name in FEATURES})

    old = NeuralNetwork([len(LEGACY_FEATURES), 4, 1], feature_names=LEGACY_FEATURES)
    new = NeuralNetwork([len(FEATURES), 4, 1], feature_names=FEATURES)
    assert DangerModelRegistry._model_matrix(old, rows).shape == (3, len(LEGACY_FEATURES))
    assert DangerModelRegistry._model_matrix(new, rows).shape == (3, len(FEATURES))


def test_proxy_event_matches_are_included_by_default_but_can_be_excluded(tmp_path, monkeypatch):
    from src.machine_learning import model_registry as registry
    from src.machine_learning.danger_dataset import FEATURES

    monkeypatch.setattr(registry, "DEMO", tmp_path / "missing_demo.csv.gz")
    monkeypatch.setattr(registry, "FULL", tmp_path / "missing_full.csv.gz")
    row = {name: 0.0 for name in FEATURES}
    row.update({"match_id": 9001, "team_name": "A", "event_id": "e1", "target": 0,
                "density_source": "proxy", "density_is_360": 0.0})
    rows = pd.DataFrame([row])

    expanded = registry.DangerModelRegistry.dataset(lambda: rows.copy(), include_proxy=True)
    measured_only = registry.DangerModelRegistry.dataset(lambda: rows.copy(), include_proxy=False)
    assert expanded["match_id"].tolist() == [9001]
    assert measured_only.empty


def test_lineup_rating_uses_shared_position_adjusted_performance_when_available():
    from src.squad.planner import lab_rating

    squad = pd.DataFrame([{
        "nome": "Kylian Mbappé",
        "papel": "ST",
        "funcao": "Atacante",
        "posicao": "ST",
        "valor_mercado_eur": None,
        "transfermarkt_id": None,
        "nota_manual": None,
    }])
    performance = pd.DataFrame([{"nome": "Kylian Mbappé", "qualidade": 8.2}])

    scored = lab_rating(squad, player_performance=performance)
    assert float(scored.loc[0, "nota"]) == 82.0
    assert "desempenho" in scored.loc[0, "nota_base"]
