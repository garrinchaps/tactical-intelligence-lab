"""v26: jogo só com placar puxa estatísticas da mesma partida em outra base."""
import pytest

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel
from src.data_hub.service import MatchDataService, espn_league_for


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")


def _m(mid, src, lvl, h, a, d="2024-03-10", comp="Premier League"):
    return {"match_id": mid, "home_team_name": h, "away_team_name": a, "match_date": d, "home_score": 2, "away_score": 1,
            "competition_name": comp, "season_name": "2023/24", "country_name": "England", "status": "FT",
            "data_source": src, "data_level": lvl}


def test_result_match_gets_stats_from_sibling(db):
    db.upsert_matches([_m(3_000_000_001, "openfootball", DataLevel.RESULT, "Arsenal FC", "Chelsea FC"),
                       _m(2_000_000_001, "fdcouk", DataLevel.BOXSCORE, "Arsenal", "Chelsea")])
    db.save_boxscore(2_000_000_001, {"team_stats": [
        {"team_name": "Arsenal", "stat_key": "shots", "stat_label": "Chutes", "value": 17, "display_value": "17"},
        {"team_name": "Chelsea", "stat_key": "shots", "stat_label": "Chutes", "value": 8, "display_value": "8"}],
        "lineups": [], "timeline": []})
    db.save_boxscore(3_000_000_001, {"team_stats": [], "lineups": [], "timeline": [
        {"minute": 12, "team_name": "Arsenal FC", "player_name": "Saka", "event_type": "Goal", "detail": "Normal Goal"}]})
    b = MatchDataService(db).load(3_000_000_001)
    assert b.level == DataLevel.BOXSCORE
    ts = b.boxscore["team_stats"]
    assert set(ts["team_name"]) == {"Arsenal FC", "Chelsea FC"} and ts["value"].sum() == 25
    assert not b.boxscore["timeline"].empty                         # os gols do openfootball ficam
    assert any("fdcouk" in n for n in b.notes)
    assert db.get_match(3_000_000_001)["data_level"] == DataLevel.BOXSCORE   # persistido


def test_result_without_any_stats_is_labelled(db):
    db.upsert_matches([_m(3_000_000_002, "openfootball", DataLevel.RESULT, "Ipswich", "Luton")])
    b = MatchDataService(db, ).load(3_000_000_002)
    assert b.level == DataLevel.RESULT and any("só traz placar" in n for n in b.notes)


def test_old_boxscore_levels_without_stats_are_downgraded(tmp_path):
    path = str(tmp_path / "hub.db")
    d1 = DataHubDB(db_path=path, schema_path="database/schema.sql")
    d1.upsert_matches([_m(4_000_000_009, "intl", DataLevel.BOXSCORE, "Brazil", "England", d="1970-06-07", comp="FIFA World Cup")])
    with d1.connect() as c:                                  # simula uma base criada antes da v26
        c.execute("PRAGMA user_version = 0")
    d2 = DataHubDB(db_path=path, schema_path="database/schema.sql")
    assert d2.get_match(4_000_000_009)["data_level"] == DataLevel.RESULT


def test_espn_league_mapping():
    assert espn_league_for({"competition_name": "Brasileiro Série A 2026", "country_name": "Brazil"}) == "bra.1"
    assert espn_league_for({"competition_name": "Premier League", "country_name": "England"}) == "eng.1"
    assert espn_league_for({"competition_name": "Copa Libertadores"}) == "conmebol.libertadores"
    assert espn_league_for({"competition_name": "Women's Super League"}) is None


def test_fdcouk_stat_keys_match_labels():
    from src.data_hub.boxscore import STAT_LABELS
    from src.data_hub.sources.fdcouk import STATS

    assert all(k in STAT_LABELS for _, _, k, _ in STATS)
