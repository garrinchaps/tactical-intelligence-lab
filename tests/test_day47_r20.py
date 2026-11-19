"""Rodada 20: apelidos de times, overall calibrado, votos do Scout, clube com 1 nome, homônimos pelo clube, feminino
fora, seleções de base, treino guiado e gráficos sem zoom."""
import sqlite3
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest

from src.data_lake.ids import player_core


class _DB:
    def __init__(self, path):
        self.db_path = str(path)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db_path)
        try:
            yield c
            c.commit()
        finally:
            c.close()


def _matches_db(tmp_path, rows):
    db = _DB(tmp_path / "m.db")
    with db.connect() as c:
        c.execute("CREATE TABLE matches (match_id INTEGER, match_date TEXT, data_source TEXT, competition_name TEXT, "
                  "home_team_name TEXT, away_team_name TEXT, home_score INT, away_score INT)")
        c.execute("CREATE TABLE match_player_stats (match_id INTEGER, team_name TEXT, player_name TEXT, position TEXT, "
                  "minutes INT, rating REAL, stats_json TEXT)")
        c.execute("CREATE TABLE match_lineups (match_id INTEGER, team_name TEXT, player_name TEXT, shirt_number INT, "
                  "position TEXT, is_starter INT, formation TEXT, coach TEXT)")
        c.executemany("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)", rows)
    return db


def test_team_alias_learned_from_shared_games():
    from src.data_hub.team_alias import learn

    m = pd.DataFrame([
        ("2026-10-04", "espn", "FC Cologne", "Bayern Munich", 1, 3), ("2026-10-04", "fotmob", "1. FC Köln", "FC Bayern München", 1, 3),
        ("2026-10-18", "espn", "Werder Bremen", "FC Cologne", 0, 0), ("2026-10-19", "fotmob", "SV Werder Bremen", "1. FC Köln", 0, 0),
        ("2026-11-01", "espn", "Leipzig", "Hoffenheim", 2, 2), ("2026-11-01", "fotmob", "RB Leipzig", "TSG Hoffenheim 1899", 2, 2),
        ("2026-10-11", "espn", "Bayern Munich Women", "Wolfsburg Women", 2, 0), ("2026-10-11", "fotmob", "Bayern München", "Wolfsburg", 2, 0),
    ], columns=["match_date", "data_source", "home_team_name", "away_team_name", "home_score", "away_score"])
    out = learn(m)
    pairs = {tuple(sorted((a, b))) for a, b in zip(out["name"], out["other"])}
    assert ("1. FC Köln", "FC Cologne") in pairs
    assert not any("Hoffenheim" in a or "Hoffenheim" in b for a, b in pairs)       # 1 jogo só não basta
    assert not any("Women" in a or "Women" in b for a, b in pairs)                 # feminino nunca junta


def test_team_alias_groups(tmp_path):
    from src.data_hub import team_alias as TA

    db = _matches_db(tmp_path, [
        (1, "2026-10-04", "espn", "Bundesliga", "FC Cologne", "Bayern Munich", 1, 3),
        (2, "2026-10-04", "fotmob", "Bundesliga", "1. FC Köln", "FC Bayern München", 1, 3),
        (3, "2026-10-18", "espn", "Bundesliga", "Werder Bremen", "FC Cologne", 0, 0),
        (4, "2026-10-18", "fotmob", "Bundesliga", "SV Werder Bremen", "1. FC Köln", 0, 0)])
    r = TA.build(db, years=10)
    assert r["pares"] >= 1
    assert "1. FC Köln" in TA.aliases_of(db, "FC Cologne")


def _universe(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    q = rng.normal(0, 1, n)
    roles = rng.choice(["ST", "CB", "GK", "CM", "LW", "RB", "AM", "DM"], n)
    return pd.DataFrame({"nome": [f"P{i}" for i in range(n)], "_core": [f"p{i}" for i in range(n)], "papel": roles,
                         "valor_mercado_eur": np.exp(14 + 1.1 * q + rng.normal(0, .6, n)), "idade": rng.integers(18, 36, n),
                         "_perf_raw": np.clip(50 + 14 * q + rng.normal(0, 12, n), 1, 99), "_conf": rng.uniform(.3, .9, n),
                         "_lvl": np.clip(.5 + .15 * q + rng.normal(0, .15, n), .1, 1),
                         "minutos_12m": rng.integers(0, 4200, n), "rating_12m": 6.8 + .3 * q + rng.normal(0, .2, n),
                         "qualidade": 50.0})


def _add(u, nm, r, v, a, pr, lv, m, rt):
    u.loc[len(u)] = {"nome": nm, "_core": player_core(nm), "papel": r, "valor_mercado_eur": v, "idade": a,
                     "_perf_raw": pr, "_conf": .9, "_lvl": lv, "minutos_12m": m, "rating_12m": rt, "qualidade": 50.0}


def test_overall_world_class_is_rare_and_ceilings_hold(tmp_path, monkeypatch):
    """Rodada 21: 90+ só para ~10 no mundo; quem jogou pouco não chega ao topo; tetos de referência respeitados."""
    from src.scout import overall as O

    monkeypatch.setattr(O, "CALIB_PATH", tmp_path / "c.json")
    u = _universe(20000)
    for x in [("Kylian Mbappé", "ST", 180e6, 27, 92, 1, 3850, 8.25), ("Erling Haaland", "ST", 200e6, 26, 90, 1, 3898, 7.82),
              ("Harry Kane", "ST", 60e6, 33, 94, .95, 4115, 8.34), ("Achraf Hakimi", "RB", 80e6, 28, 86, .95, 2668, 7.67),
              ("James Maddison", "AM", 20e6, 30, 70, 1, 229, 7.24), ("Alexander Isak", "ST", 85e6, 27, 60, 1, 1581, 7.19)]:
        _add(u, *x)
    out = O.finalize_overall(u)
    q = dict(zip(out["nome"], out["qualidade"]))
    assert q["Kylian Mbappé"] >= 90 and q["Erling Haaland"] >= 88 and q["Harry Kane"] >= 87
    assert q["Achraf Hakimi"] <= O.FAMILY_CAP["FB"]
    assert q["James Maddison"] <= 85 and q["Alexander Isak"] <= 85
    assert (out["qualidade"] >= 90).sum() <= 20                          # craque mundial é raro
    assert 58 <= out["qualidade"].median() <= 68
    rep = O.load_report()
    assert rep["distribuicao"]["90+"] <= 20 and rep["tetos"]


def test_overall_reference_scale_is_consistent(tmp_path, monkeypatch):
    from src.scout import overall as O

    monkeypatch.setattr(O, "CALIB_PATH", tmp_path / "c.json")
    out = O.finalize_overall(_universe(seed=2))
    sample = _universe(seed=2).sample(20, random_state=3)
    again = O.finalize_overall(sample, reference=out)
    assert (again["qualidade"].values == out.loc[sample.index, "qualidade"].values).all()


def test_overall_unknown_stays_unknown(tmp_path, monkeypatch):
    from src.scout import overall as O

    monkeypatch.setattr(O, "CALIB_PATH", tmp_path / "c.json")
    u = _universe(300)
    u.loc[0, ["_perf_raw", "valor_mercado_eur", "qualidade"]] = np.nan
    out = O.finalize_overall(u)
    assert pd.isna(out.loc[0, "qualidade"])                             # sem dado = sem nota (nunca zero)


def test_votes_reorder_without_removing():
    from src.scout import engine as E

    r = pd.DataFrame({"nome": ["A", "B"], "_core": ["a", "b"], "score_scout": [70.0, 68.0]})
    out = E.apply_votes(r, {"b": (2, 0), "a": (0, 1)})
    assert out["nome"].tolist() == ["B", "A"] and len(out) == 2


def test_canonical_clubs_one_name():
    from src.scout import engine as E

    u = pd.DataFrame({"nome": ["A", "B", "C"], "_core": ["a", "b", "c"],
                      "clube": ["Cruzeiro", "Cruzeiro Esporte Clube", "Cruzeiro"], "clube_observado": [True, False, True],
                      "clube_tm": [None, None, None]})
    out = E.canonical_clubs(u)
    assert set(out["clube"]) == {"Cruzeiro"} and out.loc[1, "clube_tm"] == "Cruzeiro Esporte Clube"


def test_homonyms_get_minutes_from_own_club(tmp_path):
    from src.scout import engine as E

    db = _matches_db(tmp_path, [(1, "2099-01-01", "fotmob", "Brasileirão Série A", "Cruzeiro", "Bahia", 1, 0)])
    import datetime as dt
    today = dt.date.today().isoformat()
    with db.connect() as c:
        c.execute("UPDATE matches SET match_date = ?", (today,))
        c.executemany("INSERT INTO match_player_stats VALUES (?,?,?,?,?,?,?)",
                      [(1, "Cruzeiro", "Matheus Pereira", "AM", 90, 7.5, "{}"), (1, "Bahia", "Matheus Pereira", "LB", 90, 6.4, "{}")])
    u = pd.DataFrame({"nome": ["Matheus Pereira", "Matheus Pereira"], "_core": ["matheus pereira"] * 2,
                      "clube": ["Cruzeiro Esporte Clube", "Esporte Clube Bahia"], "clube_tm": [None, None],
                      "minutos_12m": [np.nan, np.nan], "minutos": [np.nan, np.nan], "historico_ambiguo": [True, True]})
    out = E.fill_homonyms_from_club(db, u)
    assert out.loc[0, "rating_12m"] == 7.5 and out.loc[1, "rating_12m"] == 6.4


def test_women_only_players_removed(tmp_path):
    from src.data_hub import gender as G

    db = _matches_db(tmp_path, [(1, "2026-10-01", "fotmob", "Brasileirão Feminino", "Cruzeiro", "Santos", 1, 0),
                                (2, "2026-10-02", "fotmob", "Brasileirão Série A", "Cruzeiro", "Bahia", 1, 0)])
    with db.connect() as c:
        c.executemany("INSERT INTO match_player_stats VALUES (?,?,?,?,?,?,?)",
                      [(1, "Cruzeiro", "Byanca Brasil", "ST", 90, 7.0, "{}"), (2, "Cruzeiro", "Kaio Jorge", "ST", 90, 7.0, "{}")])
    G._WOMEN_PLAYERS.clear()
    df = pd.DataFrame({"nome": ["Byanca Brasil", "Kaio Jorge"]})
    assert G.drop_women_players(df, db, ["Cruzeiro"])["nome"].tolist() == ["Kaio Jorge"]


def test_youth_caps_and_trait(tmp_path):
    from src.scout import engine as E
    from src.scout.traits import add_traits

    db = _matches_db(tmp_path, [(1, "2025-10-01", "fotmob", "Copa do Mundo Sub-20", "Brazil U20", "Mexico U20", 2, 1)])
    with db.connect() as c:
        c.executemany("INSERT INTO match_player_stats VALUES (?,?,?,?,?,?,?)",
                      [(1, "Brazil U20", "Melk", "AM", 80, 7.4, "{}")])
    caps = E.youth_caps(db)
    u = pd.DataFrame({"nome": ["Melk", "Outro"], "_core": ["melk", "outro"], "idade": [19, 20], "papel": ["AM", "AM"],
                      "minutos_12m": [2600, 100]})
    u = E.merge_youth(u, caps)
    assert u.loc[0, "selecao_base_jogos"] == 1 and pd.isna(u.loc[1, "selecao_base_jogos"])
    t = add_traits(u)
    assert any(x["nome"] == "Seleção de base" for x in t.loc[0, "caracteristicas"])


def test_learning_hub_guided_training(tmp_path):
    from src.intelligence import learning_hub as LH

    ap, fp, rp = tmp_path / "a.jsonl", tmp_path / "f.jsonl", tmp_path / "r.jsonl"
    LH.record_answer("i1", "Quem mais criou perigo?", "Fulano, 0,8 xT", "A x B", "LAB", "ranking", path=ap)
    LH.record_answer("i2", "Como explorar a defesa?", "...", "A x B", "LAB", "tatica", path=ap)
    assert [r["interaction_id"] for r in LH.recent_answers(path=ap, feedback_path=fp)] == ["i2", "i1"]
    LH.record_feedback("i2", 0, path=fp)
    assert [r["interaction_id"] for r in LH.recent_answers(path=ap, feedback_path=fp)] == ["i1"]
    for i in range(2):
        LH.record_reasons(f"x{i}", False, ["Número errado"], "deveria citar o xG", "visitante", "tatica", "q", path=rp)
    rep = LH.improvement_report(path=rp)
    assert rep["negativos"] == 2 and rep["motivos"][0][0] == "Número errado" and rep["piores_tipos"][0][0] == "tatica"


def test_plots_without_toolbar():
    import plotly.graph_objects as go

    from src.ui.plot_config import NO_TOOLS, lock_figure

    f = lock_figure(go.Figure(go.Scatter(x=[1, 2], y=[1, 2])))
    assert f.layout.dragmode is False and f.layout.xaxis.fixedrange is True
    assert NO_TOOLS["displayModeBar"] is False


def test_fotmob_leagues_youth_and_new_markets():
    from src.data_hub.sources.fotmob import LEAGUES, REGIONS, YOUTH_NAMES

    assert {296, 306, 9848, 63, 536, 223} <= set(LEAGUES)
    assert "Copa do Mundo Sub-20" in YOUTH_NAMES and 8971 in REGIONS["brasil"] and REGIONS["base"]
