from src.squad.planner import deep_tactical_signals


def test_deep_tactical_signals_require_paired_sample_and_separate_shot_quality():
    profile = {
        "a_favor": {
            "xg": {"por_jogo": [{"match_id": 1, "valor": 1.2}, {"match_id": 2, "valor": 0.8},
                                {"match_id": 3, "valor": 1.5}]},
            "shots_total": {"por_jogo": [{"match_id": 1, "valor": 10}, {"match_id": 2, "valor": 8},
                                         {"match_id": 3, "valor": 12}]},
            "goals": {"por_jogo": [{"match_id": 1, "valor": 2}, {"match_id": 2, "valor": 0},
                                   {"match_id": 3, "valor": 2}]},
        },
        "contra": {
            "xg": {"por_jogo": [{"match_id": 1, "valor": 1.4}, {"match_id": 2, "valor": 0.5},
                                {"match_id": 3, "valor": 1.1}]},
            "shots_total": {"por_jogo": [{"match_id": 1, "valor": 8}, {"match_id": 2, "valor": 10},
                                         {"match_id": 3, "valor": 9}]},
        },
    }
    signals = deep_tactical_signals(profile)
    titles = {x["titulo"] for x in signals}
    assert "Qualidade média das finalizações" in titles
    assert "Perigo médio por chute sofrido" in titles
    assert "Saldo de gols em relação ao xG" in titles
    assert all(x["jogos"] == 3 for x in signals)


def test_deep_tactical_signals_hide_small_samples():
    profile = {"a_favor": {"xg": {"por_jogo": [{"match_id": 1, "valor": 1.0}]}}}
    assert deep_tactical_signals(profile) == []
