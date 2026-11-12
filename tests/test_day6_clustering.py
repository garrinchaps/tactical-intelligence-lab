"""
Testes Automatizados do Dia 6: Validação de Clusterização Espacial (K-Means + Silhouette Score),
DBSCAN e Diferenciação Matemática entre Volume Bruto de Perdas e Taxa de Exposição.
"""

import pandas as pd
import pytest
from src.preprocessing.event_cleaner import EventPreprocessor
from src.machine_learning.clustering import SpatialTacticalClustering


def test_kmeans_separates_volume_from_exposure_risk():
    """
    Cria dois clusters espaciais distintos:
    - Zona A (Meio-Campo Central: x=60, y=40): 15 perdas de posse, mas em 100 toques totais (15% de taxa de erro).
    - Zona B (Saída Lateral Direita: x=25, y=72): 10 perdas de posse em apenas 12 toques totais (83.3% de taxa de erro).
    Verifica se o modelo separa os 2 clusters com alto Silhouette Score e identifica:
    - Zona A como Maior Volume Bruto.
    - Zona B como Maior Vulnerabilidade por Exposição.
    """
    rows = []
    idx = 1

    # 1. Zona A (x~60, y~40): 15 perdas (passes incompletos) + 85 passes completos = 100 toques
    for i in range(100):
        is_err = i < 15
        rows.append(
            {
                "event_id": f"za_{idx}",
                "match_id": 606,
                "period": 1,
                "index_num": idx,
                "minute": 10,
                "second": idx % 50,
                "possession": 1,
                "possession_team_name": "Time Teste",
                "team_name": "Time Teste",
                "player_name": "Meia Central",
                "type_name": "Pass",
                "pass_outcome_name": "Incomplete" if is_err else None,
                "x": 60.0 + (i % 3) * 0.5,
                "y": 40.0 + (i % 3) * 0.5,
                "end_x": 65.0,
                "end_y": 40.0,
                "under_pressure": 0,
            }
        )
        idx += 1

    # 2. Zona B (x~25, y~72): 10 perdas + 2 passes completos = 12 toques (83.3% de erro!)
    for i in range(12):
        is_err = i < 10
        rows.append(
            {
                "event_id": f"zb_{idx}",
                "match_id": 606,
                "period": 1,
                "index_num": idx,
                "minute": 25,
                "second": idx % 50,
                "possession": 2,
                "possession_team_name": "Time Teste",
                "team_name": "Time Teste",
                "player_name": "Lateral Direito",
                "type_name": "Pass",
                "pass_outcome_name": "Incomplete" if is_err else None,
                "x": 25.0 + (i % 2) * 0.5,
                "y": 72.0 + (i % 2) * 0.5,
                "end_x": 35.0,
                "end_y": 72.0,
                "under_pressure": 1,
            }
        )
        idx += 1

    df_raw = pd.DataFrame(rows)
    df_enriched = EventPreprocessor.process_match_events(df_raw)

    res = SpatialTacticalClustering.analyze_turnover_clusters(
        df_enriched, target_team="Time Teste", k_candidates=(2, 3)
    )

    assert res["status"] == "OK"
    assert res["total_turnovers"] == 25
    assert res["optimal_k"] == 2
    assert res["silhouette_score"] > 0.80

    vol_cluster = res["highest_volume_cluster"]
    risk_cluster = res["highest_risk_exposure_cluster"]

    # O cluster de maior volume bruto deve ser a Zona A (15 perdas no Terço Médio)
    assert vol_cluster["turnovers_in_cluster"] == 15
    assert vol_cluster["tactical_third"] == "Terço Médio"

    # O cluster de maior vulnerabilidade ajustada por exposição deve ser a Zona B (83.33% no Terço Defensivo)
    assert risk_cluster["turnovers_in_cluster"] == 10
    assert risk_cluster["tactical_third"] == "Terço Defensivo"
    assert risk_cluster["turnover_rate_per_touch_pct"] == pytest.approx(83.33, abs=0.1)