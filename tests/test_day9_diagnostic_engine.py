"""
Testes Automatizados do Dia 9: Validação do Motor Central de Inteligência Tática,
Geração de Objetos de Diagnóstico e Classificação de Força da Evidência.
"""

import pandas as pd
import pytest
from src.preprocessing.event_cleaner import EventPreprocessor
from src.tactical_engine.diagnostic_engine import TacticalDiagnosticEngine


def test_diagnostic_engine_generation():
    """
    Simula uma partida sintética e verifica se o TacticalDiagnosticEngine produz
    pelo menos um diagnóstico estruturado com campos obrigatórios preenchidos e
    classificação de evidência válida.
    """
    rows = []
    idx = 1
    # Gera passes e perdas para Time A e Time B
    for i in range(25):
        rows.append(
            {
                "event_id": f"diag_{idx}",
                "match_id": 909,
                "period": 1,
                "index_num": idx,
                "minute": 10 + i,
                "second": 0,
                "possession": 1,
                "possession_team_name": "Time A" if i % 2 == 0 else "Time B",
                "team_name": "Time A" if i % 2 == 0 else "Time B",
                "player_name": f"Atleta {i}",
                "position_name": "Midfield",
                "type_name": "Pass",
                "pass_outcome_name": "Incomplete" if i % 3 == 0 else None,
                "x": 40.0 + (i * 1.5),
                "y": 20.0 + (i * 1.0),
                "end_x": 50.0 + (i * 1.5),
                "end_y": 25.0 + (i * 1.0),
                "under_pressure": 1 if i % 2 == 0 else 0,
            }
        )
        idx += 1

    df_raw = pd.DataFrame(rows)
    df_enriched = EventPreprocessor.process_match_events(df_raw)
    df_chains = EventPreprocessor.build_possession_chains(df_enriched)

    diags = TacticalDiagnosticEngine.generate_comprehensive_diagnostics(
        df_enriched, df_chains, target_team="Time A"
    )

    assert isinstance(diags, list)
    assert len(diags) >= 1

    first_diag = diags[0]
    assert "problem_title" in first_diag
    assert "phase_of_play" in first_diag
    assert "evidence_strength" in first_diag
    assert first_diag["evidence_strength"] in ["FORTE", "MODERADA", "LIMITADA"]
    assert "recommendation_plan_a" in first_diag