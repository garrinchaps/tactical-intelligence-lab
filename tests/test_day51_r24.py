"""Rodada 24 — identidade dos jogadores (id FotMob + clube + nascimento + posição), cobertura e qualidade única."""

import json

import pandas as pd

from src.data_lake.ids import player_core, team_core
from src.scout import engine as E


def _rows(items):
    r = pd.DataFrame(items)
    r["_core"] = r["player_name"].map(player_core)
    r["_club_core"] = r["team_name"].map(team_core)
    return r


def test_homonyms_with_different_fotmob_ids_stay_separate():
    r = _rows([
        {"player_name": "Otávio", "team_name": "Cruzeiro", "stats_json": json.dumps({"fotmob_id": 111})},
        {"player_name": "Otávio", "team_name": "Paris FC", "stats_json": json.dumps({"fotmob_id": 222})},
        {"player_name": "Otavio", "team_name": "Cruzeiro", "stats_json": "{}"},          # ESPN sem id, mesmo clube
        {"player_name": "Otávio", "team_name": "Bordeaux", "stats_json": "{}"},          # sem id, outro clube
    ])
    out = E.assign_person_ids(r)
    assert out.loc[0, "_pid"] == "fm111" and out.loc[1, "_pid"] == "fm222"
    assert out.loc[2, "_pid"] == "fm111"                      # junta pelo clube
    assert out.loc[3, "_pid"].startswith("nm:")               # não vira nenhum dos dois


def test_market_match_needs_identity_for_homonyms():
    p = pd.DataFrame([
        {"nome": "Otávio", "clube": "Cruzeiro", "posicao": "Goalkeeper", "funcao": "Goalkeeper",
         "nacionalidade": "Brazil", "nascimento": "2001-05-01"},
        {"nome": "Otávio", "clube": "Paris FC", "posicao": "Midfield", "funcao": "Central Midfield",
         "nacionalidade": "Brazil", "nascimento": "1994-05-04"},
    ])
    p["_core"] = p["nome"].map(player_core)
    hist = pd.DataFrame([
        {"core": "otavio#fm111", "core_nome": "otavio", "ultimo_time": "Cruzeiro", "posicao_observada": "GK",
         "nascimento_fm": "2001-05-01"},
        {"core": "otavio#fm222", "core_nome": "otavio", "ultimo_time": "Paris FC", "posicao_observada": "CM",
         "nascimento_fm": "1994-05-04"},
    ])
    keys = E.match_market_to_history(p, hist)
    assert keys.tolist() == ["otavio#fm111", "otavio#fm222"]


def test_birth_or_goalkeeper_mismatch_blocks_merge():
    p = pd.DataFrame([{"nome": "João Silva", "clube": "Bahia", "posicao": "Attack", "funcao": "Centre-Forward",
                       "nacionalidade": "Brazil", "nascimento": "1990-01-01"}])
    p["_core"] = p["nome"].map(player_core)
    hist = pd.DataFrame([{"core": "joao silva", "core_nome": "joao silva", "ultimo_time": "Bahia",
                          "posicao_observada": "ST", "nascimento_fm": "2004-01-01"}])
    assert E.match_market_to_history(p, hist).isna().all()
    hist2 = hist.assign(nascimento_fm=None, posicao_observada="GK")
    assert E.match_market_to_history(p, hist2).isna().all()


def test_unique_name_still_merges_when_club_is_outdated():
    p = pd.DataFrame([{"nome": "Kaio Jorge", "clube": "Juventus", "posicao": "Attack", "funcao": "Centre-Forward",
                       "nacionalidade": "Brazil", "nascimento": "2002-01-24"}])
    p["_core"] = p["nome"].map(player_core)
    hist = pd.DataFrame([{"core": "kaio jorge", "core_nome": "kaio jorge", "ultimo_time": "Cruzeiro",
                          "posicao_observada": "ST", "nascimento_fm": None}])
    assert E.match_market_to_history(p, hist).tolist() == ["kaio jorge"]


def test_advice_is_individual_per_matchup():
    import numpy as np

    from src.squad import advice as AD

    rng = np.random.default_rng(1)
    cols = ["drb_p90", "crs_p90", "cc_p90", "xg_p90", "tob_p90", "aer_pct", "fouled_p90", "lbp_p90", "rec_p90",
            "drb_past_p90", "duel_pct", "int_p90", "disp_p90", "fouls_p90", "tkl_p90"]
    ref = pd.DataFrame(rng.uniform(0, 1, size=(300, len(cols))), columns=cols)
    xi = [{"papel": "RW", "jogador": "Ponta A"}, {"papel": "RB", "jogador": "Lateral A"}, {"papel": "LW", "jogador": "Ponta B"},
          {"papel": "LB", "jogador": "Lateral B"}]
    a1 = {c: .5 for c in cols} | {"drb_p90": .99, "crs_p90": .95}
    a2 = {c: .5 for c in cols} | {"drb_p90": .99, "xg_p90": .97}
    d = {c: .5 for c in cols} | {"drb_past_p90": .99, "aer_pct": .02}
    base = {"tipo": "duelo", "dimensao": "drible", "gap": 70, "acao": "x"}
    i1 = AD.individualize(dict(base, atacante="Ponta A", defensor="Zag 1", papel_atacante="RW", papel_defensor="LB"),
                          xi, a1, d, ref, "4-3-3", {"momento": "eles ficam com a bola"})
    i2 = AD.individualize(dict(base, atacante="Ponta B", defensor="Zag 2", papel_atacante="LW", papel_defensor="RB"),
                          xi, a2, d, ref, "3-4-3", {})
    assert i1["passos"] != i2["passos"]
    assert any("direito" in s for s in i1["passos"]) and any("esquerdo" in s for s in i2["passos"])
    assert any("cruzamento" in s for s in i1["passos"]) and any("finalização" in s for s in i2["passos"])
    assert any("Lateral A" in s for s in i1["passos"])                    # quem apoia, do mesmo lado
    assert any("4-3-3" in s for s in i1["passos"]) and any("três zagueiros" in s for s in i2["passos"])


def test_trainer_params_have_help_and_recommendations():
    from src.intelligence.lab_ai import trainer as TR

    rec = TR.recommend({"history": {"train_loss": [1, .8, .6, .5, .4], "val_loss": [1, .9, .95, 1.0, 1.1]}}, 10, 2)
    assert set(TR.PARAMS) <= set(rec) and all(len(v[4]) > 40 for v in TR.PARAMS.values())
    assert "SUBIR" in rec["l2"] or "ALTO" in rec["l2"]


def test_shape_lines_never_one_nine_one():
    from src.analytics.tactical_identity import shape_lines

    assert shape_lines([20, 21, 22, 23, 40, 41, 42, 60, 61, 62]) == [4, 3, 3]
    assert shape_lines([25, 40, 41, 42, 43, 44, 45, 46, 47, 70])[0] >= 3
    assert shape_lines([30, 31, 32, 50, 51, 52, 53, 54, 70, 71]) == [3, 5, 2]


def test_origin_south_america_includes_brazil():
    s = pd.Series(["Brasil · Série B", "América do Sul", "Europa e outras"])
    assert E.origin_match(s, "América do Sul (com Brasil)").tolist() == [True, True, False]
    assert E.origin_match(s, "Todas").all()
    assert E.origin_group_full("", "Brazil").startswith("Brasil")
