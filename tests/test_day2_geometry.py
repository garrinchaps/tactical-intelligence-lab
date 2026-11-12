"""
Testes Automatizados do Dia 2: Geometria do Campo (18 Zonas, Zona 14, Corredores)
e Engenharia de Cadeias de Posse (Possession Chains).
"""

import pandas as pd
import pytest
from src.geometry.pitch_zones import PitchGeometry
from src.preprocessing.event_cleaner import EventPreprocessor


def test_corridors_and_zone_14_classification():
    """
    Verifica se as coordenadas (x, y) são classificadas exatamente nos 5 corredores
    do Jogo Posicional e se a Zona 14 (frontal à grande área) é detectada sem falsos positivos.
    """
    df = pd.DataFrame(
        [
            # Passe que sai do Meio-Espaço Esquerdo no Terço Médio e entra na Zona 14
            {
                "event_id": "p1",
                "match_id": 1,
                "period": 1,
                "index_num": 1,
                "minute": 10,
                "second": 0,
                "possession": 5,
                "possession_team_name": "Time A",
                "team_name": "Time A",
                "type_name": "Pass",
                "pass_outcome_name": None,
                "x": 65.0,
                "y": 24.0,
                "end_x": 88.0,
                "end_y": 40.0,
                "under_pressure": 0,
                "ball_recovery_failure": 0,
                "interception_outcome_name": None,
                "shot_statsbomb_xg": None,
            },
            # Finalização de dentro da Grande Área (x=108, y=40)
            {
                "event_id": "s1",
                "match_id": 1,
                "period": 1,
                "index_num": 2,
                "minute": 10,
                "second": 4,
                "possession": 5,
                "possession_team_name": "Time A",
                "team_name": "Time A",
                "type_name": "Shot",
                "pass_outcome_name": None,
                "x": 108.0,
                "y": 40.0,
                "end_x": 120.0,
                "end_y": 40.0,
                "under_pressure": 1,
                "ball_recovery_failure": 0,
                "interception_outcome_name": None,
                "shot_statsbomb_xg": 0.25,
            },
        ]
    )

    enriched = EventPreprocessor.process_match_events(df)

    # Verifica linha 0 (o passe)
    row0 = enriched.iloc[0]
    assert row0["origin_third"] == "Terço Médio"
    assert row0["origin_corridor"] == "Meio-Espaço Esquerdo"
    assert row0["end_corridor"] == "Corredor Central"
    assert row0["end_in_zone_14"] == 1
    assert row0["is_zone_14_entry"] == 1
    assert row0["is_progressive_action"] == 1  # Ganhou > 10 jardas em direção ao gol no campo ofensivo

    # Verifica linha 1 (o chute na grande área)
    row1 = enriched.iloc[1]
    assert row1["origin_in_box"] == 1

    # Verifica construção da Cadeia de Posse
    chains = EventPreprocessor.build_possession_chains(enriched)
    assert len(chains) == 1
    assert chains.loc[0, "entered_zone_14"] == 1
    assert chains.loc[0, "entered_box"] == 1
    assert chains.loc[0, "ended_in_shot"] == 1
    assert chains.loc[0, "chain_xg"] == pytest.approx(0.25)


def test_convex_hull_calculation():
    """
    Garante que um retângulo de pontos conhecido produza uma área geométrica positiva
    e centroide exato em (60, 40).
    """
    pts = pd.DataFrame(
        {
            "x": [40.0, 40.0, 80.0, 80.0],
            "y": [20.0, 60.0, 20.0, 60.0],
        }
    )
    hull = PitchGeometry.compute_team_convex_hull(pts, trim_outliers_pct=0.0)
    assert hull["centroid_x"] == pytest.approx(60.0)
    assert hull["centroid_y"] == pytest.approx(40.0)
    assert hull["hull_area_m2"] > 1000.0