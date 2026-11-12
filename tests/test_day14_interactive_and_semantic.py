"""
Testes Automatizados da Evolução Interativa e Alinhamento Semântico:
1. Resolução de confrontos reais vs. partidas fora da base pública (fallback de simulação sem erro 404).
2. Alinhamento semântico cirúrgico do relatório quando o `user_query` pede para anular um jogador específico.
"""

from pathlib import Path
import pandas as pd
from src.ingestion.statsbomb_loader import StatsBombDataLoader
from src.preprocessing.event_cleaner import EventPreprocessor
from src.metrics.xt_model import ExpectedThreatModel
from src.reports.report_builder import QueryIntentRouter, TacticalReportBuilder
from src.intelligence.llm_analyst import GenerativeTacticalAnalyst


def test_match_resolution_and_simulation_fallback(tmp_path: Path):
    """
    Verifica se um confronto inexistente no StatsBomb Open Data (ex: 'TimeFicticio123 x OutroTime999')
    retorna o status 'NOT_FOUND_OFFER_SIMULATION' com a mensagem correta e gera a simulação
    tática estruturada sem lançar erro 404.
    """
    loader = StatsBombDataLoader(
        db_path=str(tmp_path / "sim_test.db"),
        schema_path="database/schema.sql",
        raw_dir=str(tmp_path / "raw"),
    )

    res = loader.resolve_user_match_input("TimeFicticio123 x OutroTime999")
    assert res["status"] == "NOT_FOUND_OFFER_SIMULATION"
    assert res["is_simulation"] is True
    assert "não está disponível no StatsBomb" in res["user_message"]

    sim_df = loader.generate_tactical_simulation_match(
        res["home_team"], res["away_team"], match_id=res["match_id"]
    )
    assert len(sim_df) > 100
    # Valida que os times gerados na simulação correspondem aos nomes fornecidos na string de entrada
    assert set(sim_df["team_name"].unique()) == {"Timeficticio123", "Outrotime999"}


def test_semantic_alignment_for_specific_player_query():
    """
    Garante que quando o usuário pergunta especificamente 'Monte uma tática para anular o Lionel Messi',
    o roteador detecta o foco 'PLAYER_SPECIFIC_TACTIC', extrai o dossiê do atleta (centroide, feeder, target)
    e coloca o plano de neutralização individual no topo do relatório.
    """
    rows = [
        {
            "event_id": "p1",
            "match_id": 2026,
            "period": 1,
            "index_num": 1,
            "minute": 10,
            "second": 0,
            "possession": 1,
            "possession_team_name": "Argentina",
            "team_name": "Argentina",
            "player_name": "Rodrigo Javier De Paul",
            "pass_recipient_name": "Lionel Andrés Messi Cuccittini",
            "position_name": "Right Center Midfield",
            "type_name": "Pass",
            "pass_outcome_name": None,
            "x": 55.0,
            "y": 52.0,
            "end_x": 78.0,
            "end_y": 48.0,
            "under_pressure": 0,
        },
        {
            "event_id": "p2",
            "match_id": 2026,
            "period": 1,
            "index_num": 2,
            "minute": 10,
            "second": 4,
            "possession": 1,
            "possession_team_name": "Argentina",
            "team_name": "Argentina",
            "player_name": "Lionel Andrés Messi Cuccittini",
            "pass_recipient_name": "Julián Álvarez",
            "position_name": "Right Wing",
            "type_name": "Pass",
            "pass_outcome_name": None,
            "x": 78.0,
            "y": 48.0,
            "end_x": 104.0,
            "end_y": 40.0,
            "under_pressure": 1,
        },
        {
            "event_id": "p3",
            "match_id": 2026,
            "period": 1,
            "index_num": 3,
            "minute": 12,
            "second": 0,
            "possession": 2,
            "possession_team_name": "France",
            "team_name": "France",
            "player_name": "Kylian Mbappé Lottin",
            "pass_recipient_name": "Adrien Rabiot",
            "position_name": "Left Wing",
            "type_name": "Pass",
            "pass_outcome_name": None,
            "x": 60.0,
            "y": 15.0,
            "end_x": 75.0,
            "end_y": 25.0,
            "under_pressure": 0,
        },
    ]

    df_enriched = EventPreprocessor.process_match_events(pd.DataFrame(rows))
    df_xt = ExpectedThreatModel.enrich_events_with_xt(df_enriched)
    df_chains = EventPreprocessor.build_possession_chains(df_xt)

    user_q = "Monte uma tática para anular o Messi e cortar suas conexões."
    evidence = TacticalReportBuilder.assemble_evidence_package(
        df_events=df_xt,
        df_chains=df_chains,
        target_team="Argentina",
        match_id=2026,
        user_query=user_q,
    )

    assert evidence["metadata"]["detected_focus"] == "PLAYER_SPECIFIC_TACTIC"
    assert "Lionel Messi" in evidence["metadata"]["matched_players_in_query"]
    assert len(evidence["focused_player_deep_dive"]) == 1

    dossier = evidence["focused_player_deep_dive"][0]
    assert dossier["primary_feeder_teammate"] == "Rodrigo De Paul"
    assert dossier["primary_target_teammate"] == "Julián Álvarez"

    analyst = GenerativeTacticalAnalyst(api_key=None)
    rep = analyst.generate_tactical_report(evidence, prefer_llm=False)

    assert "Lionel Messi" in rep["report_markdown"]
    assert "Rodrigo De Paul" in rep["report_markdown"]
    assert rep["hallucination_audit"]["is_grounded"] is True