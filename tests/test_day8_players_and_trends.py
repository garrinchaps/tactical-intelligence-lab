"""
Testes Automatizados do Dia 8: Validação da Análise Individual, Motor de Substituições
e Detecção Estatística de Padrões Crônicos vs. Isolados em Múltiplas Partidas.
"""

import pandas as pd
import pytest
from src.preprocessing.event_cleaner import EventPreprocessor
from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.metrics.multi_match_analyzer import MultiMatchTrendAnalyzer


def test_player_evaluator_and_substitution_recommendation():
    """
    Simula um titular ('Meia Desgastado') que acerta 100% dos passes antes do minuto 60,
    mas cai para 20% de acerto após o minuto 60 com múltiplas perdas de posse,
    verificando se o motor recomenda sua substituição com justificativa tática e aviso de GPS.
    """
    rows = []
    idx = 1

    # 10 passes completos entre o minuto 5 e 55 (100% de acerto na 1ª janela)
    for m in range(5, 55, 5):
        rows.append(
            {
                "event_id": f"p_early_{idx}",
                "match_id": 801,
                "period": 1 if m < 45 else 2,
                "index_num": idx,
                "minute": m,
                "second": 10,
                "possession": 1,
                "possession_team_name": "Time A",
                "team_name": "Time A",
                "player_name": "Meia Desgastado",
                "position_name": "Center Midfield",
                "type_name": "Pass",
                "pass_outcome_name": None,
                "x": 55.0,
                "y": 40.0,
                "end_x": 72.0,
                "end_y": 40.0,
                "under_pressure": 0,
            }
        )
        idx += 1

    # 5 passes após o minuto 65, sendo 4 incompletos (turnovers) -> 20% de acerto (queda de 80%!)
    for i, m in enumerate([65, 68, 72, 75, 78]):
        is_err = i < 4
        rows.append(
            {
                "event_id": f"p_late_{idx}",
                "match_id": 801,
                "period": 2,
                "index_num": idx,
                "minute": m,
                "second": 20,
                "possession": 2,
                "possession_team_name": "Time A",
                "team_name": "Time A",
                "player_name": "Meia Desgastado",
                "position_name": "Center Midfield",
                "type_name": "Pass",
                "pass_outcome_name": "Incomplete" if is_err else None,
                "x": 58.0,
                "y": 42.0,
                "end_x": 65.0,
                "end_y": 40.0,
                "under_pressure": 1,
            }
        )
        idx += 1

    enriched = EventPreprocessor.process_match_events(pd.DataFrame(rows))
    sub_report = PlayerTacticalEvaluator.recommend_tactical_substitutions(
        enriched, target_team="Time A"
    )

    assert len(sub_report["recommended_substitutions"]) == 1
    rec = sub_report["recommended_substitutions"][0]
    assert rec["candidate_out"] == "Meia Desgastado"
    assert rec["priority_score"] >= 45.0
    assert "LIMITAÇÃO EXPLÍCITA DE DADOS" in sub_report["data_limitations_notice"]


def test_multi_match_separates_chronic_pattern_from_isolated_event():
    """
    Cria 3 partidas para 'Time A' onde:
    - Nas 3 partidas, o Adversário sempre progride pela esquerda dele (vulnerabilidade crônica
      no 'Setor Defensivo Direito (Lateral-Direito)').
    - Em apenas 1 das 3 partidas, o Time A comete >= 5 turnovers no próprio terço defensivo
      (classificado como 'EVENTO ISOLADO').
    """
    matches_map = {}

    for match_id in [1, 2, 3]:
        ev_list = [
            # Ação do Time A
            {
                "event_id": f"m{match_id}_a1",
                "match_id": match_id,
                "period": 1,
                "index_num": 1,
                "minute": 5,
                "second": 0,
                "possession": 1,
                "possession_team_name": "Time A",
                "team_name": "Time A",
                "player_name": "Volante A",
                "type_name": "Pass",
                "pass_outcome_name": None,
                "x": 45.0,
                "y": 40.0,
                "end_x": 75.0,
                "end_y": 40.0,
            },
            # Ação progressiva do Adversário pelo Corredor Lateral Esquerdo dele (y=10) -> Setor Defensivo Direito do Time A
            {
                "event_id": f"m{match_id}_opp1",
                "match_id": match_id,
                "period": 1,
                "index_num": 2,
                "minute": 10,
                "second": 0,
                "possession": 2,
                "possession_team_name": "Adversario",
                "team_name": "Adversario",
                "player_name": "Ponta Adv",
                "type_name": "Pass",
                "pass_outcome_name": None,
                "x": 50.0,
                "y": 12.0,
                "end_x": 85.0,
                "end_y": 10.0,
            },
        ]

        # Somente na partida 1 adicionamos 5 turnovers no terço defensivo (x=20)
        if match_id == 1:
            for k in range(5):
                ev_list.append(
                    {
                        "event_id": f"m1_err_{k}",
                        "match_id": 1,
                        "period": 1,
                        "index_num": 10 + k,
                        "minute": 20 + k,
                        "second": 0,
                        "possession": 3,
                        "possession_team_name": "Time A",
                        "team_name": "Time A",
                        "player_name": "Zagueiro A",
                        "type_name": "Pass",
                        "pass_outcome_name": "Incomplete",
                        "x": 20.0,
                        "y": 40.0,
                        "end_x": 30.0,
                        "end_y": 40.0,
                    }
                )

        matches_map[match_id] = pd.DataFrame(ev_list)

    report = MultiMatchTrendAnalyzer.analyze_team_across_matches(
        matches_map, target_team="Time A"
    )

    assert report["matches_analyzed"] == 3
    diags = {d["pattern_type"]: d for d in report["pattern_diagnostics"]}

    # A vulnerabilidade no Setor Defensivo Direito ocorreu em 3/3 jogos (100% -> PADRÃO CRÔNICO RECORRENTE)
    vuln_diag = diags["Vulnerabilidade Espacial Defensiva"]
    assert vuln_diag["classification"] == "PADRÃO CRÔNICO RECORRENTE"
    assert vuln_diag["recurrence_rate_pct"] == pytest.approx(100.0)

    # Os erros de saída de bola ocorreram em apenas 1/3 jogos (33.33% -> EVENTO ISOLADO)
    buildup_diag = diags["Risco na Saída de Bola (1º Terço)"]
    assert buildup_diag["classification"] == "EVENTO ISOLADO"
    assert buildup_diag["matches_observed"] == 1