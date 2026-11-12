"""
Testes Automatizados do Dia 3: Validação Matemática de PPDA, Vulnerabilidade Espacial
por Corredor Defensivo e Transição Defensiva (Janela de 5 Segundos Pós-Perda).
"""

import pandas as pd
import pytest
from src.preprocessing.event_cleaner import EventPreprocessor
from src.metrics.tactical_metrics import TacticalMetricsEngine


def test_ppda_and_defensive_corridor_inversion():
    """
    Valida se:
    1. O PPDA divide corretamente os passes adversários em construção (x <= 72)
       pelas ações defensivas altas (x >= 48).
    2. Um ataque progressivo do adversário pelo Corredor Lateral Esquerdo dele (y = 10)
       é contabilizado como vulnerabilidade no Setor Defensivo Direito da nossa equipe.
    """
    raw_events = pd.DataFrame(
        [
            # 4 passes do Time B na zona de construção (x <= 72), sendo o último progressivo pela esquerda (y=10)
            {
                "event_id": "b1",
                "match_id": 99,
                "period": 1,
                "index_num": 1,
                "minute": 1,
                "second": 0,
                "possession": 1,
                "possession_team_name": "Time B",
                "team_name": "Time B",
                "type_name": "Pass",
                "pass_outcome_name": None,
                "x": 25.0,
                "y": 40.0,
                "end_x": 35.0,
                "end_y": 20.0,
                "under_pressure": 0,
                "counterpress": 0,
                "ball_recovery_failure": 0,
            },
            {
                "event_id": "b2",
                "match_id": 99,
                "period": 1,
                "index_num": 2,
                "minute": 1,
                "second": 3,
                "possession": 1,
                "possession_team_name": "Time B",
                "team_name": "Time B",
                "type_name": "Pass",
                "pass_outcome_name": None,
                "x": 35.0,
                "y": 20.0,
                "end_x": 75.0,
                "end_y": 10.0,  # Corredor Lateral Esquerdo do Time B (ganho > 15 jardas cruzando meio-campo)
                "under_pressure": 0,
                "counterpress": 0,
                "ball_recovery_failure": 0,
            },
            # 2 ações defensivas de pressão alta do Time A (x >= 48)
            {
                "event_id": "a1",
                "match_id": 99,
                "period": 1,
                "index_num": 3,
                "minute": 1,
                "second": 5,
                "possession": 1,
                "possession_team_name": "Time B",
                "team_name": "Time A",
                "type_name": "Pressure",
                "pass_outcome_name": None,
                "x": 60.0,
                "y": 65.0,
                "end_x": None,
                "end_y": None,
                "under_pressure": 0,
                "counterpress": 0,
                "ball_recovery_failure": 0,
            },
            {
                "event_id": "a2",
                "match_id": 99,
                "period": 1,
                "index_num": 4,
                "minute": 1,
                "second": 6,
                "possession": 1,
                "possession_team_name": "Time B",
                "team_name": "Time A",
                "type_name": "Interception",
                "interception_outcome_name": "Won",
                "pass_outcome_name": None,
                "x": 55.0,
                "y": 68.0,
                "end_x": None,
                "end_y": None,
                "under_pressure": 0,
                "counterpress": 0,
                "ball_recovery_failure": 0,
            },
        ]
    )

    enriched = EventPreprocessor.process_match_events(raw_events)
    chains = EventPreprocessor.build_possession_chains(enriched)

    def_metrics = TacticalMetricsEngine.compute_defensive_organization(
        enriched, chains, target_team="Time A"
    )

    # 2 passes do Time B com x <= 72 divididos por 2 ações defensivas do Time A com x >= 48 -> PPDA = 1.0
    assert def_metrics["ppda"] == pytest.approx(1.0)
    assert (
        def_metrics["most_vulnerable_defensive_sector"]
        == "Setor Defensivo Direito (Lateral-Direito)"
    )


def test_defensive_transition_5s_gegenpress_window():
    """
    Garante que uma perda de posse no campo ofensivo (x >= 60) seguida de uma ação
    de counterpress dentro de 3 segundos seja contabilizada como reação pós-perda positiva.
    """
    raw_events = pd.DataFrame(
        [
            # Perda de posse do Time A no ataque (x = 85) no segundo 10
            {
                "event_id": "t1",
                "match_id": 100,
                "period": 1,
                "index_num": 1,
                "minute": 0,
                "second": 10,
                "possession": 2,
                "possession_team_name": "Time A",
                "team_name": "Time A",
                "type_name": "Dispossessed",
                "pass_outcome_name": None,
                "x": 85.0,
                "y": 40.0,
                "end_x": None,
                "end_y": None,
                "under_pressure": 1,
                "counterpress": 0,
                "ball_recovery_failure": 0,
            },
            # Reação imediata de Counterpress do Time A no segundo 13 (3s após a perda)
            {
                "event_id": "t2",
                "match_id": 100,
                "period": 1,
                "index_num": 2,
                "minute": 0,
                "second": 13,
                "possession": 3,
                "possession_team_name": "Time B",
                "team_name": "Time A",
                "type_name": "Pressure",
                "pass_outcome_name": None,
                "x": 82.0,
                "y": 42.0,
                "end_x": None,
                "end_y": None,
                "under_pressure": 0,
                "counterpress": 1,
                "ball_recovery_failure": 0,
            },
        ]
    )

    enriched = EventPreprocessor.process_match_events(raw_events)
    chains = EventPreprocessor.build_possession_chains(enriched)

    trans_def = TacticalMetricsEngine.compute_defensive_transition(
        enriched, chains, target_team="Time A"
    )

    assert trans_def["turnovers_in_attacking_half"] == 1
    assert trans_def["post_loss_5s_press_reaction_count"] == 1
    assert trans_def["post_loss_5s_press_reaction_pct"] == pytest.approx(100.0)