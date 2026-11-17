import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel


def test_opponent_elo_uses_only_results_before_target_match(tmp_path):
    from src.analytics.opponent_strength import opponent_strength_for_match

    db = DataHubDB(db_path=str(tmp_path / "elo.db"), schema_path="database/schema.sql")
    rows = []
    for i, rival in enumerate(("C", "D", "E", "F"), start=1):
        rows.append({
            "match_id": 8_000_000_000 + i, "match_date": f"2026-01-0{i}",
            "home_team_name": "A", "away_team_name": rival,
            "home_score": 3, "away_score": 0, "competition_name": "Liga",
            "season_name": "2026", "data_source": "espn", "data_level": DataLevel.RESULT,
        })
    target_id = 8_000_000_100
    rows.append({
        "match_id": target_id, "match_date": "2026-01-10",
        "home_team_name": "B", "away_team_name": "A",
        "home_score": 0, "away_score": 9, "competition_name": "Liga",
        "season_name": "2026", "data_source": "espn", "data_level": DataLevel.RESULT,
    })
    db.upsert_matches(rows)

    strength = opponent_strength_for_match(db, target_id, "B")
    assert strength["adversario"] == "A"
    assert strength["jogos_historicos"] == 4
    assert strength["elo"] > 1500
    assert strength["ajuste"] > 0
    assert strength["confianca"] == "média"

    from src.analytics.opponent_strength import opponent_strength_for_matches
    both = opponent_strength_for_matches(db, [(target_id, "B"), (target_id, "A")])
    assert both[(target_id, "B")]["adversario"] == "A"
    assert both[(target_id, "A")]["adversario"] == "B"


def test_rating_adjustment_is_small_and_explicitly_contextual():
    from src.analytics.rating_v2 import evaluate

    ref = pd.DataFrame({
        "funcao": ["ponta"] * 8,
        "xg90": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    })
    row = {"jogador": "Atacante", "equipe": "A", "funcao": "ponta", "minutos": 90, "xg90": 0.55}
    baseline = evaluate(row, ref)
    adjusted = evaluate(row, ref, {"opponent_adjustment": 0.3,
                                   "opponent_strength": {"adversario": "Rival", "nivel": 75.0}})
    assert adjusted["desempenho"] == min(10.0, round(baseline["desempenho"] + 0.3, 1))
    assert adjusted["forca_adversario"]["adversario"] == "Rival"
