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
