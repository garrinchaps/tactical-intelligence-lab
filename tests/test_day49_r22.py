"""Rodada 22: correções rápidas (contagem de jogos, rótulos, tela de carregamento, janela cmd, resultados de ontem)."""
from datetime import date

import numpy as np
import pandas as pd


def test_fmt_num_keeps_integer_zeros():
    from src.ui.components import fmt_num

    assert fmt_num(40, "{:.0f}") == "40"            # era "4" (o "4 jogos" do Comparar)
    assert fmt_num(100, "{:.0f}") == "100"
    assert fmt_num(3232, "{:.0f}") == "3232"
    assert fmt_num(3.50) == "3.5" and fmt_num(2.0) == "2"
    assert fmt_num(None) == "—"


def test_matchup_labels_are_football_words():
    from src.squad.matchups import _fmt

    for k in ("rec_p90", "disp_p90", "off_p90", "lb_p90", "crs_pct", "lbp_p90"):
        txt = _fmt(k, 1.234)
        assert k not in txt and any(c.isalpha() for c in txt)
    assert "recuperações" in _fmt("rec_p90", 5.64) and "perdeu a bola" in _fmt("disp_p90", 1.75)


def test_splash_hides_team_and_match_names():
    from src.ui.loading import splash_html

    st = {"steps": [{"nome": "Abrindo a base", "status": "ok", "s": 1.0},
                    {"nome": "Jogos que você abriu por último (1/2)", "status": "ok", "s": 0.5},
                    {"nome": "Jogos que você abriu por último (2/2)", "status": "rodando", "s": None},
                    {"nome": "Times que você abriu por último (1/1)", "status": "fila", "s": None}], "t0": 0}
    h = splash_html(st)
    assert h.count("Jogos que você abriu por último") == 1 and "(1/2)" not in h


def test_warmup_step_names_have_no_team(monkeypatch, tmp_path):
    from src.ui import warmup as W

    monkeypatch.setattr(W, "_read_recent", lambda: {"jogos": [123], "times": ["Bayern München"]})
    names = " ".join(n for n, _ in W._plan())
    assert "Bayern" not in names and "123" not in names


def test_hidden_subprocess_flags(monkeypatch):
    from src.tools import proc

    monkeypatch.setattr(proc.os, "name", "posix")
    assert proc.hidden() == {}
    r = proc.run(["python", "-c", "print(1)"], capture_output=True, text=True, timeout=20)
    assert r.stdout.strip() == "1"


def test_silent_sync_skips_when_app_open(monkeypatch, tmp_path):
    from src.data_hub import activity
    from src.tools import sync_silencioso as S

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(activity, "ui_active", lambda *a, **k: True)
    import sys

    out, err = sys.stdout, sys.stderr
    try:
        assert S.main(["--rapido"]) == 0
    finally:
        sys.stdout, sys.stderr = out, err
    assert "pulado" in (tmp_path / "data" / "sync_log.txt").read_text(encoding="utf-8")


def test_fotmob_sync_dates_uses_known_season(tmp_path, monkeypatch):
    from src.data_hub.db import DataHubDB
    from src.data_hub.sources.fotmob import LEAGUES, FotmobProvider

    db = DataHubDB(tmp_path / "t.db")
    comp = LEAGUES[268]
    db.upsert_matches([{"match_id": 12_000_000_001, "source_match_id": "1", "competition_name": comp, "season_name": "2026",
                        "match_date": "2026-10-01", "home_team_name": "A", "away_team_name": "B", "home_score": 1,
                        "away_score": 0, "status": "FT", "data_source": "fotmob", "data_level": "RESULT"}])
    fm = FotmobProvider(db, enabled=True)
    payload = {"leagues": [
        {"primaryId": 268, "matches": [{"id": 777, "home": {"id": 1, "name": "Vasco da Gama", "score": 2},
                                          "away": {"id": 2, "name": "Internacional", "score": 1},
                                          "status": {"utcTime": "2026-11-19T22:00:00Z", "finished": True, "started": True,
                                                     "scoreStr": "2 - 1"}}]},
        {"primaryId": 999999, "matches": [{"id": 1}]},                         # liga fora da lista: ignorada
        {"primaryId": 8814, "matches": [{"id": 5}]}]}                          # sem temporada na base: não chuta
    monkeypatch.setattr(fm, "_get", lambda path, params, max_age_s, cache=True: payload)
    r = fm.sync_dates([date(2026, 11, 19)])
    assert r["partidas"] == 1 and r["sem_temporada"] == 1
    with db.connect() as c:
        row = c.execute("SELECT home_team_name, home_score, season_name FROM matches WHERE source_match_id = '777'").fetchone()
    assert row == ("Vasco da Gama", 2, "2026")


def test_frozen_catalog_refreshes_after_3h(tmp_path, monkeypatch):
    from src.data_hub import db as D

    db = D.DataHubDB(tmp_path / "t.db")
    monkeypatch.setattr(D, "_frozen", lambda: True)
    v1 = db.stable_version()
    m = D.DataHubDB._ver_memo[str(db.db_path)]
    m["latest"], m["probed"] = "nova", 0
    monkeypatch.setattr(db, "catalog_version", lambda: "nova")
    assert db.stable_version() == v1                     # dentro das 3 h: congelado
    m["at"] -= D.FROZEN_SETTLE_S + 1
    assert db.stable_version() == "nova"                 # passou de 3 h: adota a versão nova


def test_status_text_explains_disabled():
    from src.data_hub import autosync as A

    assert "DESLIGADA" in A.status_text({"enabled": False})


def test_star_gap_blocks_neymar_at_small_club():
    from src.scout.engine import star_gap, transfer_realism

    buyer = {"maior_valor_jogador_eur": 3e6, "valor_elenco_eur": 25e6, "melhor_qualidade_elenco": 68,
             "orcamento_proxy_eur": 1.5e6}
    ney = {"maior_valor_eur": 180e6, "valor_mercado_eur": 12e6, "qualidade": 80, "idade": 34, "minutos_12m": 1500,
           "nacionalidade": "Brazil", "clube_valor_total_eur": 60e6}
    cap, why = star_gap(ney, buyer)
    assert cap is not None and cap <= 20 and "patamar" in why
    r = transfer_realism(ney, buyer, "Brazil", "Série B")
    assert r["score"] <= 20 and r["rotulo"] == "Fora da realidade do clube"
    young = {"maior_valor_eur": 2e6, "valor_mercado_eur": 2e6, "qualidade": 66, "idade": 21}
    assert star_gap(young, buyer) == (None, "")
    big = {"maior_valor_jogador_eur": 60e6, "valor_elenco_eur": 400e6, "melhor_qualidade_elenco": 84}
    assert star_gap(ney, big)[0] is None or star_gap(ney, big)[0] > 20        # clube grande: não é "fora da realidade"


def test_ai_filters_apply_to_both_lists():
    from src.ui.pages.scout import _apply_ai_filters

    df = pd.DataFrame({"idade": [19.8, 25, 33, None], "qualidade": [60, 70, 80, 50],
                       "valor_mercado_eur": [1e6, 5e6, 40e6, None], "nacionalidade": ["Brazil", "Argentina", "Brazil", "Chile"],
                       "realismo": [{}, {}, {"teto_patamar": 18}, {}]})
    assert len(_apply_ai_filters(df, {"age": (16, 40)})) == 3                 # estrela fora do patamar escondida
    assert len(_apply_ai_filters(df, {"age": (16, 40), "stars": True})) == 4
    young = _apply_ai_filters(df, {"age": (18, 21), "stars": True})
    assert set(young["idade"].fillna(-1)) == {19.8, -1}                        # 19,8 conta como 19; sem idade não some
    assert len(_apply_ai_filters(df, {"q": 65, "fee": 10, "stars": True})) == 1
    assert list(_apply_ai_filters(df, {"nation": "Brazil", "stars": True})["qualidade"]) == [60, 80]


def test_joint_view_defaults():
    from src.ui import context as C

    assert C.DEFAULT_LEVELS == ("EVENTS", "BOXSCORE", "RESULT")


def _mk_matches(db, rows):
    db.upsert_matches([{"match_id": mid, "competition_name": comp, "season_name": "2026", "match_date": d,
                        "home_team_name": h, "away_team_name": a, "home_score": 1, "away_score": 0,
                        "data_source": "espn", "data_level": lv} for mid, comp, d, h, a, lv in rows])


def test_women_only_players_fast_path(tmp_path):
    from src.data_hub import gender as G
    from src.data_hub.db import DataHubDB
    from src.data_lake.ids import player_core

    db = DataHubDB(tmp_path / "w.db")
    _mk_matches(db, [(500000001, "Brasileirão Feminino", "2026-05-01", "Cruzeiro", "Corinthians", "BOXSCORE"),
                     (500000002, "Série A", "2026-05-02", "Cruzeiro", "Bahia", "BOXSCORE")])
    with db.connect() as c:
        c.executemany("INSERT INTO match_player_stats (match_id, team_name, player_name) VALUES (?,?,?)",
                      [(500000001, "Cruzeiro", "Ana Souza"), (500000001, "Cruzeiro", "Gabi Lima"),
                       (500000002, "Cruzeiro", "Gabi Lima"), (500000002, "Cruzeiro", "João Silva")])
    G._WOMEN_PLAYERS.clear()
    assert G.women_only_players(db) == {player_core("Ana Souza")}      # Gabi aparece nos dois: homônimo fica


def test_catalog_memo_incremental_and_views(tmp_path):
    from src.data_hub.db import DataHubDB

    db = DataHubDB(tmp_path / "c.db")
    _mk_matches(db, [(500000010, "Série A", "2026-05-01", "Bahia", "Vitória", "RESULT"),
                     (500000011, "Série A", "2026-05-08", "Bahia", "Sport", "BOXSCORE")])
    v1 = db.stable_version(force=True)
    df = db.catalog_memo(v1)
    mine = lambda d: [m for m in d["match_id"] if m >= 500000000]
    assert mine(df) == [500000011, 500000010] and "genero" in df
    view = db.catalog_view(v1, "rich", lambda d: d[d["data_level"] != "RESULT"])
    view["x"] = 1                                                        # quem recebe pode mexer sem estragar o original
    assert "x" not in db.catalog_view(v1, "rich", lambda d: d[d["data_level"] != "RESULT"])
    _mk_matches(db, [(500000012, "Série A", "2026-05-15", "Bahia", "Ceará", "RESULT")])
    with db.connect() as c:                                              # promoção de nível sem last_synced
        c.execute("UPDATE matches SET data_level = 'EVENTS' WHERE match_id = 500000010")
    v2 = db.stable_version(force=True)
    assert v2 != v1
    df2 = db.catalog_memo(v2)
    assert mine(df2) == [500000012, 500000011, 500000010]
    assert df2.loc[df2["match_id"] == 500000010, "data_level"].iloc[0] == "EVENTS"


def test_cached_catalog_where_parser():
    from src.ui.context import _parse_where

    assert _parse_where("data_level = 'EVENTS' AND data_source IN ('statsbomb','wyscout')", ()) == [
        ("data_level", "in", ("EVENTS",)), ("data_source", "in", ("statsbomb", "wyscout"))]
    assert _parse_where("competition_name = ?", ("Série A",)) == [("competition_name", "in", ("Série A",))]
    assert _parse_where("match_date > ?", ("2020",)) is None                  # vai ao SQLite como antes
    assert _parse_where("", ()) == []


def test_fotmob_dribbles_tackles_and_rates_reach_scout():
    from src.scout import engine as E

    assert "dribbles_succeeded" in E._raw_keys(E.COUNT_KEYS["dribbles"])          # nome da FotMob
    assert "matchstats.headers.tackles" in E._raw_keys(E.COUNT_KEYS["tackles"])
    d = {"passes_acc": 80, "passes_tot": 100, "duel_won": 6, "duel_lost": 10, "aerials_won": 3, "aerials_tot": 4,
         "dribbles": 4, "dribbles_tot": 8, "shots_on_target": 5, "shots": 10, "crosses_acc": 1, "crosses_tot": 3}
    E.derived_rates(d)
    assert d["pass_accuracy_pct"] == 80.0 and d["duels_won_pct"] == 37.5 and d["dribble_pct"] == 50.0
    assert d["aerial_pct"] is None and d["cross_pct"] is None                      # amostra pequena: vazio, não zero
    df = pd.DataFrame([d, {"passes_acc": None, "passes_tot": None}])
    E.derived_rates(df)
    assert df["pass_accuracy_pct"].iloc[0] == 80.0 and pd.isna(df["pass_accuracy_pct"].iloc[1])


def test_potential_by_age_and_talent():
    from src.scout import potential as P

    u = pd.DataFrame({"papel": ["ST", "ST", "ST", "CB"], "idade": [18, 18, 31, None], "qualidade": [77, 62, 85, 70],
                      "minutos_12m": [2600, 300, 3000, 2000], "_lvl": [.9, .3, .9, .5],
                      "valor_mercado_eur": [60e6, 1e6, 50e6, 5e6], "rating_12m": [7.4, 6.4, 7.5, 6.9]})
    out = P.compute(u)
    assert out.loc[2, "potencial"] == 85                                   # 31 anos: potencial = overall
    assert out.loc[0, "potencial"] > out.loc[1, "potencial"] + 10          # jovem que joga muito em time forte
    assert 84 <= out.loc[0, "potencial"] <= 95
    assert out.loc[3, "potencial"] == 70 and "idade desconhecida" in out.loc[3, "potencial_porque"]
    assert all(out["potencial"] >= u["qualidade"])


def test_overall_learned_correction_keeps_distribution(tmp_path, monkeypatch):
    from src.scout import overall as O

    monkeypatch.setattr(O, "CALIB_PATH", tmp_path / "c.json")
    rng = np.random.default_rng(3)
    n = 6000
    q = rng.normal(0, 1, n)
    u = pd.DataFrame({"nome": [f"P{i}" for i in range(n)], "_core": [f"p{i}" for i in range(n)],
                      "papel": rng.choice(["ST", "CB", "GK", "CM", "LW", "RB"], n),
                      "valor_mercado_eur": np.exp(14 + q), "idade": rng.integers(18, 35, n),
                      "_perf_raw": np.clip(50 + 14 * q, 1, 99), "_conf": .8, "_lvl": np.clip(.5 + .15 * q, .1, 1),
                      "minutos_12m": rng.integers(500, 4000, n), "rating_12m": 6.8 + .3 * q, "qualidade": 50.0})
    from src.data_lake.ids import player_core

    rows = []
    for k, (nm, t) in enumerate(list(O.all_targets().items())[:60]):
        z = (t - 75) / 6
        rows.append({"nome": nm, "_core": player_core(nm), "papel": "ST", "valor_mercado_eur": np.exp(15.5 + z),
                     "idade": 25, "_perf_raw": float(np.clip(70 + 8 * z, 1, 99)), "_conf": .9, "_lvl": .85,
                     "minutos_12m": 3000, "rating_12m": 7.2 + .15 * z, "qualidade": 50.0})
    u = pd.concat([u, pd.DataFrame(rows)], ignore_index=True)
    out = O.finalize_overall(u)
    rep = O.load_report()
    assert rep["correcao"] and rep["correcao"]["n"] >= 25 and rep["erro_medio_alvos"] is not None
    assert (out["qualidade"] >= 90).sum() <= 20 and 55 <= out["qualidade"].median() <= 70
    assert "potencial" in out and (out["potencial"].dropna() >= out.loc[out["potencial"].notna(), "qualidade"]).all()
