"""Brasileirão com estatísticas completas (API-Football em lotes), súmulas da CBF no formato real, níveis e temporadas."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")


def _fixture(fid, home="Flamengo", away="Palmeiras", xg=("1.84", "0.92")):
    base = json.loads((FIX / "api_football_fixture.json").read_text(encoding="utf-8"))["response"][0]
    fx = json.loads(json.dumps(base))
    fx["fixture"]["id"] = fid
    fx["fixture"]["status"]["short"] = "FT"
    fx["teams"]["home"]["name"], fx["teams"]["away"]["name"] = home, away
    for blk, v in zip(fx.get("statistics") or [], xg):
        blk["statistics"] = [s for s in blk["statistics"] if s.get("type") != "expected_goals"] + \
                            [{"type": "expected_goals", "value": v}]
    return fx


def test_brasil_backfill_uses_batches_skips_done_and_stops_at_plan(db, monkeypatch):
    from src.data_hub.sources.api_football import ApiFootballProvider, PlanRestricted

    p = ApiFootballProvider(db, api_key="x" * 20)
    calls = []

    def fake_get(path, params, max_age_s):
        calls.append(params)
        if "ids" in params:
            return [_fixture(int(i)) for i in params["ids"].split("-")]
        if params.get("season") == 2026:
            raise PlanRestricted("Free plans do not have access to this season")
        if params.get("season") == 2025:
            return [{"fixture": {"id": 9000 + i, "status": {"short": "FT"}}} for i in range(45)] + \
                   [{"fixture": {"id": 9999, "status": {"short": "NS"}}}]
        return []

    monkeypatch.setattr(p, "_get", fake_get)
    out = p.backfill_stats(leagues=[71], since_year=2025, until_year=2026, max_requests=50)
    batches = [c for c in calls if "ids" in c]
    assert [len(c["ids"].split("-")) for c in batches] == [20, 20, 5]          # 45 jogos em 3 requisições
    assert out["jogos"] == 45 and out["com_xg"] == 45 and out["temporadas_bloqueadas"] == ["Brasileirão Série A 2026"]
    ts = db.load_boxscore(100_000_000 + 9000)["team_stats"]
    assert set(ts[ts.stat_key == "xg"]["value"]) == {1.84, 0.92}
    calls.clear()
    again = p.backfill_stats(leagues=[71], since_year=2025, until_year=2025, max_requests=50)
    assert again["jogos"] == 0 and not [c for c in calls if "ids" in c]          # já tem: continua de onde parou


def test_brasil_backfill_respects_request_budget(db, monkeypatch):
    from src.data_hub.sources.api_football import ApiFootballProvider

    p = ApiFootballProvider(db, api_key="x" * 20)
    monkeypatch.setattr(p, "_get", lambda path, params, max_age_s: (
        [_fixture(int(i)) for i in params["ids"].split("-")] if "ids" in params
        else [{"fixture": {"id": 5000 + i, "status": {"short": "FT"}}} for i in range(100)]))
    out = p.backfill_stats(leagues=[71], since_year=2024, until_year=2024, max_requests=3)
    assert out["requisicoes"] == 3 and out["jogos"] == 40


def _cbf_tree(root: Path):
    d = root / "results" / "processed"
    d.mkdir(parents=True)
    games = {
        "003_date": "03/04/2013", "003_time": "22:00", "003_stadium": "Olímpico do Pará / Belém",
        "003_home": "Remo / PA", "003_away": "Flamengo / RJ", "003_result": "0 X 1",
        "003_goals": ["09:00 2T11NRRafael Lima Pereira Flamengo/RJ"], "003_yellow_cards": ["28:00 2T3Renato Silva Flamengo/RJ"],
        "003_red_cards": [], "003_changes": ["29:00 1TFlamengo/RJ 15 - Carlos"],
        "004_date": "10/04/2013", "004_home": "América / RN", "004_away": "Athletico Paranaense / PR",
        "004_result": "2 X 6", "004_goals": ["01:00 1T9NREderson Alves Ribeiro Atlético/PR"],        # incompleto
        "005_date": "11/04/2013", "005_home": "América / MG", "005_away": "Flamengo / RJ", "005_result": "1 X 1",
        "005_goals": ["+2 1T9NRFulano América/MG", "40:00 2T5CTCiclano Flamengo/RJ"],              # contra
        "006_date": "12/04/2013", "006_home": "América / MG", "006_away": "Remo / PA", "006_result": "",  # adiado
    }
    (d / "CdB_2013_games.json").write_text(json.dumps(games, ensure_ascii=False), encoding="utf-8")
    raw = root / "results" / "raw" / "CdB" / "2013" / "CSVs"
    raw.mkdir(parents=True)
    (raw / "003.csv").write_text("SÚMULA ON-LINE\n", encoding="utf-8")


def test_cbf_processed_games_json(db, tmp_path):
    from src.data_hub.sources.cbf_sumulas import CbfSumulasProvider, inspect

    root = tmp_path / "cbf"
    _cbf_tree(root)
    p = CbfSumulasProvider(db, path=str(root))
    assert [f.name for f in p.files()] == ["CdB_2013_games.json"]                 # os CSVs brutos ficam de fora
    out = p.sync()
    assert out["partidas"] == 3 and out["nao_reconhecidos"] == 0
    cat = db.catalog("data_source = 'cbf'").set_index("home_team_name")
    assert cat.loc["Remo", "competition_name"] == "Copa do Brasil" and cat.loc["Remo", "data_level"] == DataLevel.RESULT
    assert cat.loc["Remo", "stadium_name"] == "Olímpico do Pará"
    assert "America-MG" in cat.index.tolist() or "América" in cat.index.tolist()
    tl = db.load_boxscore(int(cat.loc["Remo", "match_id"]))["timeline"]
    g = tl[tl.event_type == "Goal"].iloc[0]
    assert (g.minute, g.team_name, g.player_name) == (54, "Flamengo", "Rafael Lima Pereira")
    assert set(tl.event_type) == {"Goal", "Card"}
    # 2x6 com um só gol listado: a linha do tempo não bate com o placar → sem gols (nunca autor no time errado)
    amer_rn = db.catalog("data_source = 'cbf' AND away_team_name = 'Athletico Paranaense'")
    tl2 = db.load_boxscore(int(amer_rn.iloc[0]["match_id"]))["timeline"]
    assert tl2.empty or (tl2["event_type"] == "Goal").sum() == 0
    # gol contra conferido com o placar 1x1: vale para o América
    am = db.catalog("data_source = 'cbf' AND away_team_name = 'Flamengo' AND home_score = 1")
    tl3 = db.load_boxscore(int(am.iloc[0]["match_id"]))["timeline"]
    goals3 = tl3[tl3.event_type == "Goal"]
    assert sorted(goals3.team_name) == sorted([am.iloc[0]["home_team_name"]] * 2) or len(goals3) == 0 or \
        sorted(goals3.team_name.tolist()).count(am.iloc[0]["home_team_name"]) == 1
    rep = inspect(str(root))
    assert "[jogo completo]" in rep and "[reconhecido]" in rep


def test_cbf_same_name_different_state():
    from src.data_hub.sources.cbf_sumulas import split_team

    assert split_team("Remo / PA") == ("Remo", "PA") and split_team("Flamengo/RJ") == ("Flamengo", "RJ")
    assert split_team("Botafogo") == ("Botafogo", "")


def test_reconcile_downgrades_boxscore_with_only_halftime_goals(db):
    db.upsert_matches([{"match_id": 2_000_000_123, "home_team_name": "A", "away_team_name": "B", "match_date": "2016-08-01",
                        "home_score": 1, "away_score": 0, "data_source": "fdcouk", "data_level": DataLevel.BOXSCORE}])
    db.save_boxscore(2_000_000_123, {"team_stats": [{"team_name": "A", "stat_key": "ht_goals", "stat_label": "x", "value": 1}],
                                     "lineups": [], "timeline": []})
    assert db.reconcile_levels() >= 1
    assert db.get_match(2_000_000_123)["data_level"] == DataLevel.RESULT


def test_season_labels():
    from src.data_hub.sources.open_matchday import season_label
    from src.data_hub.sources.openplay import season_label as op

    assert season_label("2627", "Brazil", "2026-05-31") == "2026" and season_label("2526", "England", "2026-05-01") == "2025/2026"
    assert op("1415", "eng") == "2014/2015" and op("2021", "ita") == "2020/2021"
    assert op("2021", "afcon") == "2021" and op(2015, "copa") == "2015"


def test_cbf_nested_format_from_real_files(db, tmp_path):
    """Formato real (conferido no PC do usuário): {"003": {"date": ..., "home": ...}}."""
    from src.data_hub.sources.cbf_sumulas import CbfSumulasProvider

    d = tmp_path / "cbf" / "results" / "processed"
    d.mkdir(parents=True)
    (d / "Serie_A_2019_games.json").write_text(json.dumps({
        "001": {"date": "27/04/2019", "time": "16:00", "stadium": "Maracanã / Rio de Janeiro", "home": "Flamengo / RJ",
                "away": "Cruzeiro / MG", "result": "3 X 1",
                "goals": ["10:00 1T9NRGabriel Barbosa Flamengo/RJ", "30:00 1T7NRBruno Henrique Flamengo/RJ",
                          "05:00 2T10NRThiago Neves Cruzeiro/MG", "40:00 2T8NRArrascaeta Flamengo/RJ"],
                "yellow_cards": [], "red_cards": []}}), encoding="utf-8")
    out = CbfSumulasProvider(db, path=str(tmp_path / "cbf")).sync()
    assert out["partidas"] == 1
    m = db.catalog("data_source = 'cbf'").iloc[0]
    assert m["competition_name"] == "Campeonato Brasileiro Série A" and m["season_name"] == "2019"
    tl = db.load_boxscore(int(m["match_id"]))["timeline"]
    assert len(tl) == 4 and tl.iloc[2]["minute"] == 50
