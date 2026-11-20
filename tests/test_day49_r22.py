"""Rodada 22: correções rápidas (contagem de jogos, rótulos, tela de carregamento, janela cmd, resultados de ontem)."""
from datetime import date

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
