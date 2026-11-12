"""
Testes Automatizados do Dia 13: Validação de Integração de Ponta a Ponta (E2E)
de todo o TACTICAL INTELLIGENCE LAB.
"""

from pathlib import Path
import pandas as pd
import pytest

from src.preprocessing.event_cleaner import EventPreprocessor
from src.metrics.tactical_metrics import TacticalMetricsEngine
from src.networks.pass_network import PassingNetworkAnalyzer
from src.metrics.xt_model import ExpectedThreatModel
from src.machine_learning.clustering import SpatialTacticalClustering
from src.machine_learning.supervised import PossessionDangerClassifier
from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.tactical_engine.diagnostic_engine import TacticalDiagnosticEngine
from src.reports.report_builder import TacticalReportBuilder, NumericHallucinationGuard
from src.intelligence.llm_analyst import GenerativeTacticalAnalyst


def test_end_to_end_tactical_lab_pipeline(tmp_path: Path):
    """
    Executa o pipeline completo (E2E) de ponta a ponta sobre uma partida simulada robusta:
    1. Ingestão e Pré-processamento + Cadeias de Posse.
    2. Métricas Coletivas (PPDA, Bloco, Corredores).
    3. Rede de Passes (NetworkX) e xT.
    4. Clusterização (K-Means/DBSCAN).
    5. Treinamento e Inferência Supervisionada (XGBoost).
    6. Avaliação Individual e Substituições.
    7. Motor de Diagnósticos Causa-Efeito.
    8. Geração de Relatório e Auditoria Anti-Alucinação.
    """
    rows = []
    idx = 1
    teams = ["Equipe Alfa", "Equipe Beta"]

    # Ajustado de 40 para 80 eventos para garantir volume suficiente de posses distintas
    for i in range(80):
        t_name = teams[i % 2]
        opp_name = teams[(i + 1) % 2]
        rows.append(
            {
                "event_id": f"e_{idx}",
                "match_id": 1313,
                "period": 1 if i < 40 else 2,
                "index_num": idx,
                "minute": (i // 2) + 1,
                "second": (i * 7) % 60,
                "possession": 1 + (i // 3),  # Garante mais de 20 posses válidas
                "possession_team_name": t_name,
                "team_name": t_name,
                "player_name": f"Atleta {t_name[:3]} {i % 4}",
                "pass_recipient_name": f"Atleta {t_name[:3]} {(i + 1) % 4}",
                "position_name": "Midfield",
                "type_name": "Pass" if i % 5 != 0 else "Shot",
                "pass_outcome_name": "Incomplete" if i % 7 == 0 else None,
                "shot_statsbomb_xg": 0.35 if i % 5 == 0 else 0.0,
                "x": 20.0 + (i * 1.5),
                "y": 10.0 + (i * 1.1),
                "end_x": 35.0 + (i * 1.5),
                "end_y": 15.0 + (i * 1.1),
                "under_pressure": 1 if i % 3 == 0 else 0,
            }
        )
        idx += 1

    df_raw = pd.DataFrame(rows)

    # 1. Pré-processamento e Cadeias
    df_enriched = EventPreprocessor.process_match_events(df_raw)
    df_xt = ExpectedThreatModel.enrich_events_with_xt(df_enriched)
    df_chains = EventPreprocessor.build_possession_chains(df_xt)

    assert not df_chains.empty

    # 2 & 3. Métricas, Grafos e xT para 'Equipe Alfa'
    summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
        df_xt, df_chains, "Equipe Alfa"
    )
    net_res = PassingNetworkAnalyzer.build_pass_network(
        df_xt, "Equipe Alfa", until_first_sub=False
    )
    xt_sum = ExpectedThreatModel.compute_team_xt_summary(df_xt, "Equipe Alfa")
    assert summary["team_name"] == "Equipe Alfa"
    assert net_res["graph_metrics"]["nodes_count"] > 0
    assert "total_xt_generated" in xt_sum

    # 4. Clusterização Espacial
    km = SpatialTacticalClustering.analyze_turnover_clusters(df_xt, "Equipe Alfa")
    db = SpatialTacticalClustering.analyze_recovery_density_dbscan(df_xt, "Equipe Alfa")
    assert "total_turnovers" in km
    assert "total_recoveries" in db

    # 5. ML Supervisionado (XGBoost)
    clf = PossessionDangerClassifier(
        model_dir=str(tmp_path / "trained"),
        eval_dir=str(tmp_path / "eval"),
    )
    # Cria partidas falsas adicionais para permitir GroupSplit
    df_chains_multi = pd.concat(
        [df_chains.assign(match_id=m) for m in [1311, 1312, 1313]],
        ignore_index=True,
    )
    metrics_ml = clf.train_and_evaluate(df_chains_multi)
    assert metrics_ml["xgboost_metrics"]["test_roc_auc"] >= 0.50

    # 6. Jogadores e Substituições
    players = PlayerTacticalEvaluator.evaluate_team_players(df_xt, "Equipe Alfa")
    subs = PlayerTacticalEvaluator.recommend_tactical_substitutions(
        df_xt, "Equipe Alfa"
    )
    assert not players.empty
    assert "data_limitations_notice" in subs

    # 7. Diagnósticos Causa-Efeito
    diags = TacticalDiagnosticEngine.generate_comprehensive_diagnostics(
        df_xt, df_chains, "Equipe Alfa"
    )
    assert isinstance(diags, list)

    # 8. Relatório e Guardrail Anti-Alucinação
    evidence = TacticalReportBuilder.assemble_evidence_package(
        df_events=df_xt,
        df_chains=df_chains,
        target_team="Equipe Alfa",
        match_id=1313,
        user_query="Analise a organização defensiva e ofeciva.",
        classifier=clf,
    )
    analyst = GenerativeTacticalAnalyst(api_key=None)
    report_res = analyst.generate_tactical_report(evidence, prefer_llm=False)

    assert report_res["engine_used"] == "LOCAL_DETERMINISTIC_ENGINE"
    assert report_res["hallucination_audit"]["is_grounded"] is True
    assert len(report_res["report_markdown"]) > 500