"""Rodada 16: avaliações separadas de jogadores, função tática, nível de liga, seleções reconhecidas."""

import numpy as np
import pandas as pd


def _games(n_players=24, n_games=20, comp="Liga X", seed=0):
    from src.scout import evaluation as EV

    rng = np.random.default_rng(seed)
    rows = []
    teams = [f"T{i}" for i in range(6)]
    for p in range(n_players):
        team = teams[p % 6]
        reserve = p == 0                                   # P0 = reserva com poucos minutos e números ótimos
        for gidx in range(n_games if not reserve else 4):
            r = {"match_id": gidx * 10 + p % 6, "team_name": team, "player_name": f"P{p}", "core": f"p{p}",
                 "comp": comp, "season": "2026", "day": f"2026-0{1 + gidx % 9}-{10 + gidx % 18}",
                 "minutes": 25 if reserve else 90, "starter": 0 if reserve else 1, "rating": rng.normal(7, .4),
                 "team_poss": 50.0, "opponent": teams[(p + gidx + 1) % 6], "home": gidx % 2 == 0,
                 "role": "ST", "result": "V"}
            for m in EV.METRICS:
                r[m] = float(rng.poisson(1.0))
            if reserve:
                r["goals"], r["xg"] = 2.0, 1.5
            rows.append(r)
    return pd.DataFrame(rows)


def test_reserve_with_few_minutes_never_in_season_ranking():
    from src.scout import evaluation as EV

    g = _games()
    agg = EV.aggregate(g, {})
    ev = EV.evaluate(agg)
    p0 = ev.set_index("player_name").loc["P0"]
    assert pd.isna(p0["temporada"]) and p0["minutes"] == 100
    assert ev["temporada"].notna().sum() >= 20
    assert (ev.dropna(subset=["temporada"])["min_share"] >= .35).all()
    # poucos minutos: desempenho puxado para perto da média da função
    assert abs(p0["desempenho_90"] - 50) < abs(p0["desempenho_bruto"] - 50)


def test_usage_counts_starts_subs_and_share():
    from src.scout import evaluation as EV

    ev = EV.aggregate(_games(), {}).set_index("player_name")
    assert ev.loc["P0", "subs"] == 4 and ev.loc["P0", "starts"] == 0
    assert ev.loc["P1", "starts"] == 20 and 0 < ev.loc["P1", "min_share"] <= 1


def test_league_level_estimate_and_cross_league_score():
    from src.scout import evaluation as EV

    assert EV.prior_level("Brasileirão Série A") == .8
    assert EV.prior_level("Brasileirão Série B") == .6
    assert EV.prior_level("Brasileirão Série C") == .48
    assert EV.prior_level("Premier League") == 1.0
    a = EV.evaluate(EV.aggregate(_games(comp="Premier League", seed=1), {}))
    b = EV.evaluate(EV.aggregate(_games(comp="Brasileirão Série C", seed=1), {}))
    # mesmo desempenho relativo dentro da liga → a régua entre ligas favorece a liga mais forte
    assert a["geral_entre_ligas"].max() > b["geral_entre_ligas"].max()


def test_function_and_profile_are_explainable():
    from src.scout import evaluation as EV

    ev = EV.evaluate(EV.aggregate(_games(), {}))
    assert ev["funcao"].isin(["atacante de área", "atacante de apoio", "atacante completo", "centroavante"]).all()
    row = ev.dropna(subset=["temporada"]).iloc[0].to_dict()
    p = EV.profile(row, ev)
    assert "amostra" in p and p["nao_observavel"] and isinstance(p["fortes"], list)


def test_validation_flags_zero_minutes_and_reserves():
    from src.scout import evaluation as EV

    g = _games()
    ev = EV.evaluate(EV.aggregate(g, {}))
    v = EV.validate(g, ev)
    assert v["sem_minutos_no_ranking"] == 0 and v["reservas_no_ranking_temporada"] == 0


def test_more_national_teams_recognized_but_not_clubs():
    from src.squad.planner import national_team_key as k

    assert k("Greece") == "greece" and k("Korea Republic") == "south korea" and k("Australia") == "australia"
    assert k("Brazil U20") == "brazil"
    assert k("Monaco") == "" and k("Flamengo") == "" and k("Barcelona") == ""
