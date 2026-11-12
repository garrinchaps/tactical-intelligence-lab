"""
Testes Automatizados do Dia 5: Validação do Modelo Expected Threat (xT)
e Detecção de Passes que Quebram Linhas Defensivas.
"""

import pandas as pd
import pytest
from src.preprocessing.event_cleaner import EventPreprocessor
from src.metrics.xt_model import ExpectedThreatModel


def test_xt_generation_and_line_breaking():
    """
    Verifica se um passe do campo de defesa (x=30) para o terço ofensivo (x=90)
    resulta em ganho positivo de xT e ativa a flag de passe que quebra linhas.
    """
    df_raw = pd.DataFrame(
        [
            {
                "event_id": "xt_1",
                "match_id": 777,
                "period": 1,
                "index_num": 1,
                "minute": 15,
                "second": 0,
                "possession": 3,
                "possession_team_name": "Time X",
                "team_name": "Time X",
                "player_name": "Meia Criativo",
                "position_name": "Central Midfield",
                "type_name": "Pass",
                "pass_outcome_name": None,
                "x": 35.0,
                "y": 40.0,
                "end_x": 88.0,
                "end_y": 42.0,
                "under_pressure": 0,
            }
        ]
    )

    enriched = EventPreprocessor.process_match_events(df_raw)
    xt_df = ExpectedThreatModel.enrich_events_with_xt(enriched)

    row = xt_df.iloc[0]
    assert row["delta_xt"] > 0.0
    assert row["is_line_breaking_pass"] == 1
    assert row["end_third"] == "Terço Ofensivo"