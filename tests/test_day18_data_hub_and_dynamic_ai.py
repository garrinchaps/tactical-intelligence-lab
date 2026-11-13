"""
Dia 18 — Data Hub multi-fonte, busca universal e IA dinâmica.

Cobre (offline, sem rede):
1. Registro de fontes: faixas de ID e níveis de dado.
2. Banco: migração, catálogo sem rebaixar nível, boxscore, cota de API.
3. Conversores: Wyscout (trecho real CC BY 4.0), API-Football e ESPN (fixtures no formato documentado).
4. Busca: interpretação de datas/times, deduplicação entre fontes e sugestões.
5. IA dinâmica: fora do escopo, recorte de minuto/lado, foco no adversário, boxscore sem coordenadas,
   e todas as respostas aprovadas pelo guardião.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel, source_from_internal_id, to_internal_id, to_source_id
from src.data_hub.search import QueryParser, UniversalMatchFinder
from src.data_hub.sources.api_football import ApiFootballProvider
from src.data_hub.sources.espn import EspnProvider
from src.data_hub.sources.statsbomb import StatsBombProvider
from src.data_hub.sources.wyscout import WyscoutConverter, WyscoutProvider, fix_text
from src.data_hub.xg import estimate_xg
from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst
from src.intelligence.query_understanding import QueryUnderstanding
from src.metrics.xt_model import ExpectedThreatModel
from src.preprocessing.event_cleaner import EventPreprocessor

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=tmp_path / "hub.db", schema_path="database/schema.sql")


@pytest.fixture(scope="module")
def wyscout_events():
    payload = json.loads((FIX / "wyscout_2058017_excerpt.json").read_text(encoding="utf-8"))
    raw = WyscoutConverter.convert(payload, to_internal_id("wyscout", 2058017))
    df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(raw))
    return raw, df, EventPreprocessor.build_possession_chains(df)


def test_registry_id_namespaces():
    assert source_from_internal_id(3869685) == "statsbomb"
    wy = to_internal_id("wyscout", 2058017)
    assert source_from_internal_id(wy) == "wyscout" and to_source_id(wy) == 2058017
    assert source_from_internal_id(to_internal_id("api_football", 1180001)) == "api_football"
    assert source_from_internal_id(to_internal_id("espn", 401700001)) == "espn"
    assert source_from_internal_id(880001) == "simulated"


def test_catalog_never_downgrades_level(db):
    rec = {"match_id": 101, "home_team_name": "A", "away_team_name": "B", "data_level": DataLevel.EVENTS,
           "data_source": "statsbomb", "competition_name": "Teste"}
    assert db.upsert_matches([rec])["added"] == 1
    db.upsert_matches([{**rec, "data_level": DataLevel.RESULT}])
    assert db.get_match(101)["data_level"] == DataLevel.EVENTS


def test_api_usage_quota_counter(db):
    assert db.api_usage_today("api_football") == 0
    db.register_api_call("api_football", 3)
    assert db.api_usage_today("api_football") == 3


def test_wyscout_conversion_is_real_and_consistent(wyscout_events):
    raw, df, chains = wyscout_events
    assert fix_text("Kant\\u00e9") == "Kanté"
    assert {"Pass", "Shot", "Duel"} <= set(raw["type_name"])
    # coordenadas no padrão StatsBomb (120 x 80)
    assert raw["x"].max() <= 120.0 and raw["y"].max() <= 80.0
    # gol contra de Mandžukić aos 18' (minuto 17 no padrão de contagem)
    og = raw[raw["type_name"] == "Own Goal Against"]
    assert len(og) == 1 and "Mand" in og.iloc[0]["player_name"]
    # recebedor inferido na grande maioria dos passes certos
    ok = raw[(raw["type_name"] == "Pass") & raw["pass_outcome_name"].isna()]
    assert ok["pass_recipient_name"].notna().mean() > 0.9
    # posições inferidas a partir do papel + localização média
    assert raw.loc[raw["player_name"] == "Luka Modrić", "position_name"].iloc[0].endswith("Midfield")
    assert len(chains) > 10


def test_lab_xg_model_behaves():
    close = estimate_xg(110, 40)
    far = estimate_xg(85, 40)
    assert 0 < far < close < 1
    assert estimate_xg(108, 40, is_penalty=True) == 0.76
    assert estimate_xg(110, 40, is_header=True) < close


def test_wyscout_index_parser():
    md = ("|[2058017](files/2058017.json)|France - Croatia, 4 - 2|July 15, 2018 at 5:00:00 PM GMT+2|"
          "matches_World_Cup.json|\n")
    recs = WyscoutProvider.parse_index(md)
    assert recs[0]["home_team_name"] == "France" and recs[0]["away_score"] == 2
    assert recs[0]["match_date"] == "2018-07-15" and recs[0]["data_level"] == DataLevel.EVENTS


def test_statsbomb_match_parser():
    raw = [{"match_id": 3869685, "match_date": "2022-12-18", "home_score": 3, "away_score": 3,
            "competition": {"competition_id": 43, "competition_name": "FIFA World Cup", "country_name": "International"},
            "season": {"season_id": 106, "season_name": "2022"},
            "home_team": {"home_team_id": 779, "home_team_name": "Argentina"},
            "away_team": {"away_team_id": 771, "away_team_name": "France"},
            "competition_stage": {"name": "Final"}, "match_status_360": "available"}]
    rec = StatsBombProvider.parse_matches(raw, {})[0]
    assert rec["round_name"] == "Final" and rec["has_360_data"] == 1 and rec["data_level"] == DataLevel.EVENTS


def test_api_football_and_espn_boxscore_parsers(db):
    fx = json.loads((FIX / "api_football_fixture.json").read_text(encoding="utf-8"))["response"][0]
    rec, box = ApiFootballProvider.parse_fixture(fx)
    assert rec["data_level"] == DataLevel.BOXSCORE and rec["home_score"] == 2
    poss = {s["team_name"]: s["value"] for s in box["team_stats"] if s["stat_key"] == "possession_pct"}
    assert poss == {"Flamengo": 58.0, "Palmeiras": 42.0}
    assert any(e["extra_minute"] == 3 for e in box["timeline"])
    db.upsert_matches([rec])
    db.save_boxscore(rec["match_id"], box)
    loaded = db.load_boxscore(rec["match_id"])
    assert len(loaded["lineups"]) == 6 and loaded["player_stats"].iloc[0]["stats"]["goals"] == 1

    summ = json.loads((FIX / "espn_summary.json").read_text(encoding="utf-8"))
    rec2, box2 = EspnProvider.parse_summary(summ, "bra.1", 401700001)
    assert rec2["data_level"] == DataLevel.BOXSCORE and rec2["stadium_name"] == "Mineirão"
    pass_pct = [s["value"] for s in box2["team_stats"] if s["stat_key"] == "pass_accuracy_pct"]
    assert pass_pct == [84.0, 81.0]  # 0.84 da ESPN vira 84%


def test_query_parser_dates_and_teams():
    today = date(2026, 11, 12)
    q = QueryParser.parse("Flamengo x Palmeiras ontem", today=today)
    assert q.teams == ["flamengo", "palmeiras"] and q.date_from == date(2026, 11, 11)
    q = QueryParser.parse("Real Madrid x Barcelona da última rodada", today=today)
    assert q.teams == ["real madrid", "barcelona"] and q.wants_latest
    q = QueryParser.parse("Argentina França 18/12/2022", today=today)
    assert q.date_from == date(2022, 12, 18)
    assert QueryParser.parse("3869685").match_id == 3869685


def test_finder_dedups_sources_and_suggests(db):
    base = {"competition_name": "FIFA World Cup", "home_score": 4, "away_score": 2, "match_date": "2018-07-15"}
    db.upsert_matches([
        {**base, "match_id": 8658, "home_team_name": "France", "away_team_name": "Croatia",
         "data_source": "statsbomb", "data_level": DataLevel.EVENTS},
        {**base, "match_id": to_internal_id("wyscout", 2058017), "home_team_name": "France",
         "away_team_name": "Croatia", "data_source": "wyscout", "data_level": DataLevel.EVENTS},
    ])
    res = UniversalMatchFinder(db).find("França x Croácia", allow_remote=False)
    assert len(res["candidates"]) == 1
    top = res["candidates"].iloc[0]
    assert top["data_source"] == "statsbomb" and "wyscout" in top["also_in"]
    res = UniversalMatchFinder(db).find("França x Croácia 2014", allow_remote=False)
    assert res["status"] == "NOT_FOUND" and not res["suggestions"].empty


def test_query_understanding_scope():
    roster = ["Luka Modrić", "Marcelo Brozović", "Antoine Griezmann"]
    sc = QueryUnderstanding.parse("A coxinha é melhor que o hambúrguer?", roster)
    assert sc.category == "off_topic" and not sc.in_scope
    sc = QueryUnderstanding.parse("Como foi a compactação defensiva do lado esquerdo no minuto 30?", roster)
    assert (sc.minute_from, sc.minute_to, sc.side, sc.phase) == (25, 35, "left", "defensive")
    sc = QueryUnderstanding.parse("Como o Modric foi abastecido no segundo tempo?", roster)
    assert sc.players == ["Luka Modrić"] and sc.period == 2
    sc = QueryUnderstanding.parse("Como a Croácia pressionou a saída da França?", roster, ["France", "Croatia"])
    assert sc.team_focus == "opponent" and "pressing" in sc.metrics


def test_dynamic_analyst_scoped_and_grounded(wyscout_events):
    _, df, chains = wyscout_events
    meta = {"match_id": to_internal_id("wyscout", 2058017), "data_level": DataLevel.EVENTS, "data_source": "wyscout"}
    ai = DynamicTacticalAnalyst(api_key="")
    off = ai.answer("A coxinha é melhor que o hambúrguer?", "France", meta, df, chains, prefer_llm=False)
    assert off["engine_used"] == "LOCAL_SCOPE_GUARD" and off["evidence"] is None

    r = ai.answer("Como foi a defesa da França pelo lado esquerdo entre 10 e 25 minutos?", "France", meta, df, chains,
                  prefer_llm=False)
    blocks = r["evidence"]["blocos"]
    assert "defesa_no_recorte" in blocks and "ataque_no_recorte" not in blocks
    assert r["scope"]["minute_from"] == 10 and r["scope"]["side"] == "left"
    assert "Resumo executivo" in r["report_markdown"]
    assert r["hallucination_audit"]["is_grounded"] is True, r["hallucination_audit"]

    r2 = ai.answer("Como o Modric foi abastecido?", "France", meta, df, chains, prefer_llm=False)
    assert any(k.startswith("jogador::Luka Modri") for k in r2["evidence"]["blocos"])
    assert r2["hallucination_audit"]["is_grounded"] is True


def test_dynamic_analyst_boxscore_is_honest_about_space():
    fx = json.loads((FIX / "api_football_fixture.json").read_text(encoding="utf-8"))["response"][0]
    rec, box = ApiFootballProvider.parse_fixture(fx)
    frames = {"team_stats": pd.DataFrame(box["team_stats"]), "lineups": pd.DataFrame(box["lineups"]),
              "timeline": pd.DataFrame(box["timeline"]), "player_stats": pd.DataFrame(box["player_stats"])}
    ai = DynamicTacticalAnalyst(api_key="")
    r = ai.answer("Como o Flamengo defendeu pelo lado esquerdo no segundo tempo?", "Flamengo", rec,
                  boxscore=frames, prefer_llm=False)
    assert "não traz coordenadas" in r["report_markdown"]
    assert r["hallucination_audit"]["is_grounded"] is True, r["hallucination_audit"]
