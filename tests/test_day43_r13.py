"""Rodada 13: régua do Scout (pico, liga, minutos recentes, precocidade), características, porquês, quadro do plano."""

import numpy as np
import pandas as pd


def _pool(n=80, role="AM", seed=0):
    from src.scout import engine as E

    rng = np.random.default_rng(seed)
    spec = E.ROLE_METRICS[E.ROLE_FAMILY[role]] if role not in E.ROLE_METRICS else E.ROLE_METRICS[role]
    d = pd.DataFrame({m: rng.uniform(0, 1, n) for m, _, _ in spec})
    d["papel"], d["nome"] = role, [f"P{i}" for i in range(n)]
    d["minutos_12m"] = rng.uniform(900, 3000, n)
    d["minutos"] = d["minutos_12m"] * 2
    d["valor_mercado_eur"] = rng.uniform(1e6, 3e7, n)
    d["idade"] = rng.uniform(20, 32, n)
    d["clube"] = [f"C{i % 16}" for i in range(n)]
    d["clube_valor_total_eur"] = [(i % 16 + 1) * 2e7 for i in range(n)]
    d["clube_liga"] = ["Forte" if i % 16 >= 8 else ("Media" if i % 16 >= 4 else "Fraca") for i in range(n)]
    return d


def test_veteran_star_in_weak_league_keeps_high_quality():
    from src.scout import engine as E

    d = _pool()
    spec = E.ROLE_METRICS.get("AM") or E.ROLE_METRICS["ATT_MID"]
    for m, _, high in spec:
        d.loc[0, m] = 1.0 if high else 0.0
    d.loc[0, ["clube", "clube_valor_total_eur", "clube_liga", "idade", "valor_mercado_eur", "minutos_12m"]] = \
        ["C0", 2e7, "Fraca", 39, 1.5e7, 2400]
    d["valor_pico_3a_eur"] = d["valor_mercado_eur"]
    d.loc[0, "valor_pico_3a_eur"] = 3.5e7 / .8 * 1.5
    q = E.add_quality_scores(d).set_index("nome")["qualidade"]
    assert q["P0"] >= 80, q["P0"]


def test_zero_recent_minutes_does_not_borrow_old_sample():
    from src.scout import engine as E

    d = _pool()
    d.loc[1, ["minutos_12m", "minutos"]] = [0, 6000]
    out = E.add_quality_scores(d).set_index("nome")
    assert out.loc["P1", "confianca_pct"] < 75


def test_precocity_rewards_value_for_age():
    from src.scout import engine as E

    d = pd.DataFrame({"idade": [18, 18, 18, 18, 18, 30], "valor_mercado_eur": [1.2e7, 1e6, 5e5, 8e5, 2e6, 5e7],
                      "minutos_12m": [1700, 100, 0, 300, 500, 3000]})
    p = E.precocity(d)
    assert p.iloc[0] == p.iloc[:5].max() and np.isnan(p.iloc[5])


def test_traits_only_for_outliers_with_reason():
    from src.scout.traits import add_traits

    n = 40
    d = pd.DataFrame({"papel": ["ST"] * n, "minutos_12m": [1500] * n, "goals_p90": np.linspace(0.05, 0.5, n),
                      "shots_p90": [2.0] * n, "idade": [27] * n})
    d.loc[n - 1, "goals_p90"] = 1.2
    out = add_traits(d)
    top = out.iloc[-1]["caracteristicas"]
    assert any(t["nome"] == "Artilheiro" for t in top) and "gols por 90" in top[0]["porque"]
    assert out.iloc[0]["caracteristicas"] == [] or all(t["nome"] != "Artilheiro" for t in out.iloc[0]["caracteristicas"])
    short = pd.DataFrame({"papel": ["ST"], "minutos_12m": [100], "goals_p90": [3.0], "shots_p90": [3.0], "idade": [27]})
    assert add_traits(short).iloc[0]["caracteristicas"] == []


def test_why_chosen_compares_with_current_starter():
    from src.scout import engine as E

    roster = pd.DataFrame({"nome": ["Titular"], "papel": ["RB"], "qualidade": [60]})
    w = E.why_chosen({"papel_alvo": "RB", "qualidade": 72, "idade": 21, "potencial_teto": 82,
                      "realismo": {"score": 80, "rotulo": "Viável", "motivos": ["a"]}}, roster)
    assert any("titular" in x.lower() for x in w["porque"])
    w2 = E.why_chosen({"papel_alvo": "RB", "qualidade": 50, "rating_12m": 6.5, "minutos_12m": 400}, roster)
    assert len(w2["atencao"]) >= 2


def test_planned_roster_and_depth():
    from src.ui.plan_board import depth_rows, planned_roster

    roster = pd.DataFrame({"nome": ["A", "B", "C"], "papel": ["ST", "ST", "GK"], "qualidade": [70, 50, 65],
                           "idade": [25, 33, 30]})
    r = planned_roster(roster, [{"nome": "Novo", "papel_alvo": "GK", "qualidade": 75}], {"B": "Vender"})
    assert set(r["nome"]) == {"A", "C", "Novo"}
    rows = {d["role"]: d for d in depth_rows(r)}
    assert any("só uma opção" in x for x in rows["ST"]["atencao"])
    assert rows["GK"]["players"][0]["nome"] == "Novo"
