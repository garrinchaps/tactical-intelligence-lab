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
