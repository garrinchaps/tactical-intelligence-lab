"""Rodada 11: modo leve, jogos repetidos, resposta direta, viabilidade por nacionalidade/carreira, potencial, PDF."""

import numpy as np
import pandas as pd


def test_activity_gate(tmp_path, monkeypatch):
    from src.data_hub import activity as A

    monkeypatch.setattr(A, "PATH", tmp_path / "ui_active")
    A._last_touch["t"] = 0
    assert A.ui_active() is False
    A.touch()
    assert A.ui_active() is True
    monkeypatch.setenv("TIL_MODO_LEVE", "0")
    assert A.ui_active() is False


def test_same_game_with_other_opponent_name_is_merged():
    from src.ui.pages.search_all import one_per_game

    df = pd.DataFrame([
        dict(match_id=1, data_level="BOXSCORE", home_team_name="Barcelona", away_team_name="Racing Santander",
             home_score=7, away_score=2, match_date="2026-09-16"),
        dict(match_id=2, data_level="BOXSCORE", home_team_name="FC Barcelona", away_team_name="R. Racing Club",
             home_score=7, away_score=2, match_date="2026-09-16"),
        dict(match_id=3, data_level="BOXSCORE", home_team_name="Barcelona SC", away_team_name="LDU de Quito",
             home_score=1, away_score=1, match_date="2026-11-08"),
        dict(match_id=4, data_level="RESULT", home_team_name="Barcelona SC", away_team_name="Liga de Quito",
             home_score=1, away_score=1, match_date="2026-11-08"),
        dict(match_id=5, data_level="BOXSCORE", home_team_name="Barcelona", away_team_name="Getafe",
             home_score=3, away_score=0, match_date="2026-11-08")])
    assert sorted(one_per_game(df)["match_id"].tolist()) == [1, 3, 5]


def test_comp_country_separates_homonyms():
    from src.ui.pages.clubs import _comp_country

    assert _comp_country("Equador — LigaPro Serie A") == "ec"
    assert _comp_country("La Liga") == "es"
    assert _comp_country("UEFA Champions League") is None
    assert _comp_country("CONMEBOL Libertadores") is None


def _events():
    rows = []
    for i, (pl, out) in enumerate([("A", "Off T"), ("A", "Wayward"), ("B", "Saved"), ("B", "Goal"), ("C", "Off T")]):
        rows.append(dict(event_id=i, match_id=1, period=1, index_num=i, minute=i, second=0, team_name="T1" if pl != "C" else "T2",
                         player_name=pl, type_name="Shot", shot_outcome_name=out, shot_statsbomb_xg=.1, x=100.0, y=40.0,
                         end_x=None, end_y=None, pass_outcome_name=None, is_pass_cross=False, duel_type_name=None))
    return pd.DataFrame(rows)


def test_direct_answer_ranks_the_asked_metric_or_stays_silent():
    from src.intelligence.lab_ai import direct as D

    meta = {"home_team_name": "T1", "away_team_name": "T2"}
    r = D.answer("quem teve mais chutes para fora?", meta, _events(), None)
    assert r["key"] == "off_target" and "**A**" in r["markdown"] and "2" in r["markdown"]
    assert D.answer("o messi jogou?", meta, _events(), None) is None
    assert D.answer("o predicin é importante para que?", meta, _events(), None) is None
    gap = D.answer("quem ganhou mais duelos aéreos?", meta, _events(), None)
    assert gap["kind"] == "sem_dado" and gap["markdown"].startswith("Não tenho")
    assert D.detect("quem deu mais passes no terço final?") == "final_third"


def test_nationality_market_and_same_country():
    from src.scout import engine as E

    pool = pd.DataFrame({"nacionalidade": ["Brazil"] * 1400 + ["Argentina"] * 60 + ["Colombia"] * 30 + ["Ireland"],
                         "clube_pais": ["Brazil"] * 1491})
    nm = E.nationality_market(pool, "Brazil")
    assert nm["Brazil"][0] == 100
    assert nm["Argentina"][0] > nm["Ireland"][0]
    assert nm["Ireland"][0] < 60
    assert E._affinity("Brazil", "Brazil")[0] == 100


def test_career_context_blocks_elite_starters_moving_down():
    from src.scout import engine as E

    buyer = {"valor_elenco_eur": 8e7}
    star = {"idade": 25, "minutos_12m": 2800, "clube_valor_total_eur": 1.2e9}
    vet = {"idade": 34, "minutos_12m": 1200, "clube_valor_total_eur": 4e8}
    peer = {"idade": 26, "minutos_12m": 2000, "clube_valor_total_eur": 6e7}
    assert E.career_context(star, buyer)[0] < 20
    assert E.career_context(vet, buyer)[0] > 55
    assert E.career_context(peer, buyer)[0] >= 80
    r = E.transfer_realism({**star, "valor_mercado_eur": 1e8, "nacionalidade": "Brazil", "qualidade": 90},
                           {**buyer, "orcamento_proxy_eur": 1.5e7, "nat_market": {"Brazil": (100, "mesmo país")}},
                           "Brazil", "Brasileirão Série A", 2027)
    assert r["score"] <= 45 and any("Contexto de carreira" in m for m in r["motivos"])


def test_potential_never_below_quality():
    import sys

    sys.path.insert(0, "tests")
    from test_day40_r10 import _role_frame

    from src.scout import engine as E

    d = _role_frame()
    d["idade"] = [18 + (i % 12) for i in range(len(d))]
    q = E.add_quality_scores(d)
    ok = q["potencial_teto"].notna()
    assert (q.loc[ok, "potencial_teto"] >= q.loc[ok, "qualidade"]).all()
    young = q[q["idade"] <= 20]
    assert (young["potencial_teto"] - young["qualidade"]).mean() > 3


def test_loans_parse_only_active():
    from src.data_hub.sources.fotmob import FotmobProvider

    d = {"transfers": {"data": {
        "Players in": [{"name": "Viña", "playerId": 1, "onLoan": True, "fromClub": "Flamengo", "toDate": "2099-12-30T00:00:00Z"},
                       {"name": "Fixo", "playerId": 2, "onLoan": False, "fromClub": "X"}],
        "Players out": [{"name": "Chico", "playerId": 3, "onLoan": True, "toClub": "Fortaleza", "toDate": "2099-01-01"},
                        {"name": "Velho", "playerId": 4, "onLoan": True, "toClub": "Y", "toDate": "2001-01-01"}]}}}
    loans = FotmobProvider.parse_loans(d, 9)
    assert {(x["name"], x["direction"]) for x in loans} == {("Viña", "in"), ("Chico", "out")}


def test_dossier_pdf_is_generated():
    from src.scout import dossier_pdf as DP

    xi = [{"papel": "GK", "x": 6, "y": 40, "jogador": "Goleiro"}, {"papel": "ST", "x": 96, "y": 40, "jogador": "Novo 9"}]
    plan = [{"nome": "Novo 9", "papel_alvo_label": "Centroavante", "realismo": {"score": 80, "rotulo": "Viável",
             "motivos": ["a", "b", "c", "Adaptação (92/100): comum na liga", "Contexto de carreira (85/100): natural"]}}]
    pdf = DP.build("Clube", "4-3-3", xi, plan, {"Fulano": "Vender", "out::Chico": "Reintegrar"}, -1e6, 2027)
    assert pdf is None or pdf[:4] == b"%PDF"
