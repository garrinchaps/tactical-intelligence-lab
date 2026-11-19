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


def test_matchups_find_clear_duel_and_respect_thresholds():
    from src.squad import matchups as MU

    rng = np.random.default_rng(1)
    ref = pd.DataFrame({"drb_p90": rng.uniform(0, 2, 200), "drb_past_p90": rng.uniform(0, 2, 200),
                        "aer_pct": rng.uniform(20, 80, 200), "fouled_p90": rng.uniform(0, 3, 200),
                        "fouls_p90": rng.uniform(0, 3, 200), "duel_pct": rng.uniform(30, 70, 200),
                        "tob_p90": rng.uniform(0, 5, 200), "int_p90": rng.uniform(0, 3, 200)})
    my_xi = [{"papel": "RW", "jogador": "Ponta", "x": 100, "y": 70}]
    rv_xi = [{"papel": "LB", "jogador": "Lateral", "x": 30, "y": 10}]
    ms = pd.DataFrame([{"player_name": "Ponta", "mins": 900, "jogos": 10, "drb_p90": 1.95, "aer_pct": 50,
                        "fouled_p90": 1.0, "duel_pct": 50, "tob_p90": 1.0}])
    rs = pd.DataFrame([{"player_name": "Lateral", "mins": 900, "jogos": 10, "drb_past_p90": 1.9, "aer_pct": 50,
                        "fouls_p90": 1.0, "duel_pct": 50, "int_p90": 1.5}])
    f = MU.duel_findings(my_xi, rv_xi, ms, rs, ref, "Nós", "Eles", attack=True)
    assert f and f[0]["dimensao"] == "drible" and f[0]["nivel"] == "escancarado" and f[0]["acao"].startswith("FORÇAR")
    assert MU.duel_findings(my_xi, rv_xi, ms, rs, ref, "Nós", "Eles", attack=False) == []


def test_double_pitch_and_cards_render():
    from src.ui import matchday_view as MV

    h = MV.double_pitch([{"jogador": "A", "x": 10, "y": 40, "qualidade": 7}], [{"jogador": "B", "x": 10, "y": 40}],
                        "Nós", "Eles", {"B": 1})
    assert "A" in h and "B" in h and "#F59E0B" in h
    c = MV.finding_card(1, {"titulo": "Drible", "nivel": "claro", "evidencia": "x", "acao": "FORÇAR: y", "base": "z"})
    assert "FORÇAR" in c


def test_brain_feedback_moves_weight(tmp_path, monkeypatch):
    from src.intelligence import lab_brain as LB

    monkeypatch.setattr(LB, "ROOT", tmp_path)
    monkeypatch.setattr(LB, "STATE", tmp_path / "brain.json")
    monkeypatch.setattr(LB, "LOG", tmp_path / "log.jsonl")
    assert LB.weight("confrontos", "drible") == 1.0
    for _ in range(4):
        LB.feedback("confrontos", "drible", True)
    LB.feedback("confrontos", "aereo", False)
    assert LB.weight("confrontos", "drible") > 1.15 and LB.weight("confrontos", "aereo") < 1.0
    assert {r["tipo de análise"] for r in LB.table()} == {"drible", "aereo"}


def test_fuzzy_exploit_monotonic():
    from src.squad.matchups import fuzzy_exploit

    assert fuzzy_exploit(95, 95) > fuzzy_exploit(80, 70) > fuzzy_exploit(65, 65)
    assert 0 <= fuzzy_exploit(30, 30) <= 100


def test_course_has_simple_text_for_every_question():
    from src.intelligence import course as C

    assert set(C.SIMPLE) == {f"Q{i}" for i in range(1, 13)}
    assert all(len(a) > 60 and b for a, b in C.SIMPLE.values())


def test_opening_the_database_does_not_build_heavy_indexes(tmp_path):
    """Abrir o banco não pode criar os índices pesados (travava app e testes numa base de 300 mil jogos)."""
    from src.data_hub.db import SPEED_INDEXES, DataHubDB

    db = DataHubDB(db_path=tmp_path / "x.db", schema_path="database/schema.sql")
    assert set(db.missing_speed_indexes()) == {n for n, _ in SPEED_INDEXES}
    assert set(db.ensure_speed_indexes()) == {n for n, _ in SPEED_INDEXES}
    assert db.missing_speed_indexes() == []


def test_homonym_gets_history_by_club():
    from src.scout import engine as E

    tm = pd.DataFrame({"nome": ["Zé Lucas", "Zé Lucas"], "clube": ["Cruzeiro", "Outro FC"], "posicao": ["Midfield"] * 2,
                       "funcao": ["Defensive Midfield"] * 2, "nascimento": ["2008-01-01", "1995-01-01"],
                       "valor_mercado_eur": [None, 1e5], "transfermarkt_id": ["1", "2"]})
    hist = pd.DataFrame([{"core": "ze lucas", "ultimo_time": "Cruzeiro", "minutos_12m": 1737, "jogos_12m": 25,
                          "rating_12m": 6.9, "historico_temporadas": [], "ultimos_jogos": []}])
    u = E.build_market_universe(tm, hist).set_index("clube")
    assert u.loc["Cruzeiro", "minutos_12m"] == 1737
    assert pd.isna(u.loc["Outro FC", "minutos_12m"]) and bool(u.loc["Outro FC", "historico_ambiguo"])


def test_one_per_game_keeps_two_legs_with_same_score():
    from src.ui.pages.search_all import one_per_game

    df = pd.DataFrame([dict(match_id=1, data_level="BOXSCORE", home_team_name="Cruzeiro", away_team_name="Atlético-MG",
                            home_score=2, away_score=0, match_date="2025-08-27", competition_name="Copa do Brasil"),
                       dict(match_id=2, data_level="BOXSCORE", home_team_name="Cruzeiro", away_team_name="Atlético-MG",
                            home_score=2, away_score=0, match_date="2025-09-11", competition_name="Copa do Brasil")])
    assert sorted(one_per_game(df)["match_id"]) == [1, 2]


def test_assistant_trainer_uses_weak_labels_and_records_curve(tmp_path):
    import json

    from src.intelligence.lab_ai import trainer as TR
    from src.intelligence.lab_ai.facts import N_FEATURES
    from src.intelligence.lab_ai.selector import Selector

    rng = np.random.default_rng(0)
    shown = tmp_path / "shown.jsonl"
    with shown.open("w", encoding="utf-8") as f:
        for i in range(40):
            facts = []
            for key in ("passes_total", "long_balls_accurate", "corners"):
                feats = list(rng.uniform(0, 1, N_FEATURES))
                feats[1] = 0.9 if key == "long_balls_accurate" else 0.1     # sinal que separa o fato certo
                facts.append({"key": key, "features": feats})
            f.write(json.dumps({"interaction_id": str(i), "question": "quantas bolas longas o time fez?", "facts": facts}) + "\n")
    sel = Selector(root=tmp_path / "reg")
    r = TR.train(epochs=60, sel=sel, shown_path=shown, feedback_path=tmp_path / "none.jsonl")
    assert r["n_perguntas"] == 40 and len(r["history"]["val_loss"]) >= 2
    assert Selector(root=tmp_path / "reg").meta["versions"][-1]["history"]["train_loss"]
    assert "sugerido" in TR.suggest(Selector(root=tmp_path / "reg").meta["versions"][-1])


def test_pagerank_rewards_beating_strong_teams():
    from src.analytics.pagerank import team_strength

    m = pd.DataFrame([("A", "B", 2, 0), ("B", "C", 1, 0), ("C", "D", 3, 0), ("D", "A", 0, 1), ("C", "A", 0, 0)],
                     columns=["home_team_name", "away_team_name", "home_score", "away_score"])
    t = team_strength(m).set_index("time")
    assert t["forca_pagerank"].idxmax() == "A" and t.loc["D", "forca_pagerank"] == 0


def test_trainer_metrics_and_auto_search(tmp_path):
    import json

    from src.intelligence.lab_ai import trainer as TR
    from src.intelligence.lab_ai.facts import N_FEATURES

    rng = np.random.default_rng(3)
    shown = tmp_path / "shown.jsonl"
    with shown.open("w", encoding="utf-8") as f:
        for i in range(30):
            facts = []
            for key in ("passes_total", "long_balls_accurate", "corners"):
                feats = list(rng.uniform(0, 1, N_FEATURES))
                feats[1] = 0.95 if key == "long_balls_accurate" else 0.05
                facts.append({"key": key, "features": feats})
            f.write(json.dumps({"interaction_id": str(i), "question": "quantas bolas longas?", "facts": facts}) + "\n")
    X, y, w, g, _ = TR.build_dataset(shown, tmp_path / "x.jsonl")
    good = np.zeros(N_FEATURES)
    good[1] = 10.0
    ev = TR.evaluate(good, X, y, g)
    assert ev["acerto_1o_fato"] == 1.0 and ev["auc"] > 0.9
    grid = TR.auto_search(epochs=20, shown_path=shown, feedback_path=tmp_path / "x.jsonl")
    assert len(grid) == 9 and grid[0]["acerto_medio"] is not None


def test_team_version_changes_only_with_team_data(tmp_path):
    from src.data_hub.db import DataHubDB

    db = DataHubDB(db_path=tmp_path / "v.db", schema_path="database/schema.sql")
    v1 = db.team_version(["Time A"], ttl_s=0)
    assert v1 == db.team_version(["Time A"], ttl_s=0)
    assert v1.startswith("t:")
