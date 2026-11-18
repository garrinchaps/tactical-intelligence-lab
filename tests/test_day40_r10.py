"""Rodada 10: masculino×feminino, qualidade do Scout, números arrumados, mapa de dados e inteligência do jogador."""

import numpy as np
import pandas as pd


def test_women_competitions_never_mix_with_men_team():
    from src.data_hub.gender import comp_sql, is_women_competition, keep_same_gender

    assert is_women_competition("Frauen-Bundesliga") and is_women_competition("Liga F (Espanha)")
    assert is_women_competition("Première Ligue (França)") and not is_women_competition("Bundesliga")
    assert "NOT" in comp_sql(["Bayern München"], "m") and "NOT" not in comp_sql(["Bayern München (W)"], "m")
    df = pd.DataFrame({"competition_name": ["Bundesliga", "Frauen-Bundesliga"], "jogador": ["Kane", "Bühl"]})
    assert keep_same_gender(df, ["Bayern München"])["jogador"].tolist() == ["Kane"]


def test_gender_filter_runs_in_sqlite():
    import sqlite3

    from src.data_hub.gender import comp_sql

    c = sqlite3.connect(":memory:")
    c.execute("create table matches (match_id int, competition_name text, home_team_name text)")
    c.executemany("insert into matches values (?,?,?)", [(1, "Bundesliga", "Bayern"), (2, "Frauen-Bundesliga", "Bayern"),
                                                        (3, "Champions League Feminina", "Bayern")])
    ids = [r[0] for r in c.execute("select match_id from matches m where home_team_name='Bayern'" + comp_sql(["Bayern"], "m"))]
    assert ids == [1]


def _role_frame():
    from src.scout import engine as E

    spec = E.ROLE_METRICS.get("ST") or E.ROLE_METRICS.get("FWD")
    rng = np.random.default_rng(0)
    n = 60
    d = pd.DataFrame({m: rng.uniform(0, 1, n) for m, _, _ in spec})
    d["papel"], d["nome"] = "ST", [f"P{i}" for i in range(n)]
    d["minutos_12m"], d["valor_mercado_eur"] = rng.uniform(900, 3000, n), rng.uniform(1e5, 2e7, n)
    d["clube"] = [f"C{i % 10}" for i in range(n)]
    d["clube_valor_total_eur"] = [(i % 10 + 1) * 1e7 for i in range(n)]
    for m, _, high in spec:                                       # P0 = craque; P1 = 21 minutos com números perfeitos
        d.loc[0, m] = d.loc[1, m] = 1.0 if high else 0.0
    d.loc[0, ["minutos_12m", "valor_mercado_eur", "clube", "clube_valor_total_eur"]] = [2600, 1e8, "C9", 1e9]
    d.loc[1, ["minutos_12m", "valor_mercado_eur", "clube", "clube_valor_total_eur"]] = [21, np.nan, "C0", 1e6]
    return d


def test_scout_quality_shrinks_tiny_samples_and_rewards_level():
    from src.scout import engine as E

    q = E.add_quality_scores(_role_frame()).set_index("nome")["qualidade"]
    assert q["P0"] >= 85                       # craque de clube forte, temporada inteira
    assert q["P1"] <= 55                       # 21 minutos não viram nota de elite
    assert q["P0"] == q.max()


def test_tidy_numbers_integer_ages_and_two_decimals():
    from src.ui.components import tidy_numbers

    t = tidy_numbers(pd.DataFrame({"Idade": [23.8, 19.2], "xG /90": [0.12345, 1.0], "Minutos": [745.6, 21.0]}))
    assert t["Idade"].tolist() == [23, 19]
    assert t["xG /90"].tolist() == [0.12, 1.0]
    assert t["Minutos"].tolist() == [746, 21]


def _events():
    rows, idx = [], 0

    def add(**k):
        nonlocal idx
        idx += 1
        base = dict(event_id=f"e{idx}", match_id=1, period=1, index_num=idx, minute=idx // 3, second=0, possession=idx,
                    team_name="A", player_name="Meia", position_name="CM", type_name="Pass", under_pressure=None,
                    pass_outcome_name=None, pass_body_part="Right Foot", x=50.0, y=40.0, end_x=55.0, end_y=40.0,
                    is_pass_cross=False, is_pass_Switch=False, shot_statsbomb_xg=None, shot_outcome_name=None,
                    duel_type_name=None, duel_outcome_name=None, pass_recipient_name=None, shot_body_part_name=None)
        base.update(k)
        rows.append(base)
    for i in range(30):                         # 30 passes curtos para trás, quase todos certos, pé direito
        add(end_x=44.0)
    for i in range(10):                         # sob pressão: metade errada
        add(under_pressure=True, pass_outcome_name="Incomplete" if i % 2 else None)
    add(type_name="Dispossessed", x=40.0)
    add(type_name="Shot", team_name="B", player_name="Atacante", x=110.0, y=40.0, shot_statsbomb_xg=0.3,
        shot_outcome_name="Saved")
    return pd.DataFrame(rows)


def test_player_intel_types_and_honesty():
    from src.intelligence.lab_ai import player_intel as P

    r = P.match_intel(_events(), "Meia")
    kinds = {s["tipo"] for s in r["afirmacoes"]}
    assert {"fato", "hipótese"} <= kinds
    txt = " ".join(s["texto"] for s in r["afirmacoes"])
    assert "Sob pressão" in txt and "Pé direito" in txt
    assert any(s["tipo"] == "padrão" and "pé direito" in s["texto"] for s in r["afirmacoes"])
    assert "sucesso" not in txt or "não medido" in txt       # nunca inventa o que a fonte não mede
    assert P.patterns([r])[0]["texto"].startswith("Só 1 jogo")
    act = P.analyze_action(_events(), "e41")
    assert any("Um lance isolado" in s["texto"] for s in act["afirmacoes"])


def test_data_map_declares_gaps():
    from src.intelligence.lab_ai.availability import data_map, summary_line

    dm = data_map({"data_source": "fotmob"}, None, {"team_stats": pd.DataFrame({"stat_key": ["xg"], "value": [1]})})
    assert dm["nivel"] == 1
    off = {r["analise"] for r in dm["linhas"] if not r["disponivel"]}
    assert any("onde cada ação" in x for x in off)
    assert "Não medido aqui" in summary_line(dm)
    dm2 = data_map({}, _events(), None)
    assert dm2["nivel"] == 2


def test_asked_player_found_without_punctuation():
    from src.intelligence.lab_ai.engine import asked_player

    df = pd.DataFrame({"player_name": ["Kylian Mbappé Lottin", "Lionel Andrés Messi Cuccittini"]})
    assert asked_player("Como jogou o Mbappé?", df) == "Kylian Mbappé Lottin"
    assert asked_player("e o Messi, foi bem?", df) == "Lionel Andrés Messi Cuccittini"
    assert asked_player("quem venceu?", df) is None


def test_vuln_cards_have_fact_pattern_interpretation_hypothesis():
    from src.ui.vuln_view import cards_html

    h = cards_html([{"titulo": "X é muito driblado", "gravidade": 80, "evidencia": "2.1 vezes driblado por 90",
                     "explorar": "atacar o lado dele", "base": "6 jogos, 453 min"}])
    for k in ("Fato:", "Padrão:", "Interpretação:", "Como explorar:", "Hipótese a confirmar:"):
        assert k in h
