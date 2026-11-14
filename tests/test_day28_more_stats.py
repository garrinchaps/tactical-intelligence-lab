"""v28: mais jogos com estatísticas — xG do Understat no catálogo, histórico da ESPN e mais divisões do fdcouk."""
from datetime import date

import pandas as pd
import pytest

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")


@pytest.fixture()
def lake(tmp_path, monkeypatch):
    import src.data_lake.lake as L

    monkeypatch.setattr(L, "HAS_DUCKDB", False)
    return L.Lake(root=tmp_path / "lake", sqlite_path=tmp_path / "hub.db")


def _us(lake, rows):
    lake.write("us_partidas", pd.DataFrame(rows), source="Understat", connector="t")


def _m(mid, src, lvl, h, a, d="2024-03-10"):
    return {"match_id": mid, "home_team_name": h, "away_team_name": a, "match_date": d, "home_score": 2, "away_score": 1,
            "competition_name": "Premier League", "season_name": "2023/24", "country_name": "England", "status": "FT",
            "data_source": src, "data_level": lvl}


def _row(uid, h, a, d="2024-03-10", xh=1.8, xa=0.6):
    return {"understat_id": uid, "liga": "Premier League", "temporada": "2023/2024", "data": d, "mandante": h,
            "visitante": a, "gols_mandante": 2, "gols_visitante": 1, "xg_mandante": xh, "xg_visitante": xa}


def test_understat_xg_promotes_score_only_and_creates_missing(db, lake):
    from src.data_lake.understat_link import understat_id_for, understat_into_catalog

    db.upsert_matches([_m(3_000_000_001, "openfootball", DataLevel.RESULT, "Arsenal FC", "Chelsea FC"),
                       _m(3_000_000_002, "openfootball", DataLevel.RESULT, "Everton FC", "Fulham FC", d="2024-03-11")])
    _us(lake, [_row(22001, "Arsenal", "Chelsea"),                       # mesma partida → ganha xG
               _row(22002, "Everton", "Fulham", d="2024-03-11"),       # idem (vira estatística)
               _row(22003, "Zenit St. Petersburg", "Spartak Moscow")])  # não existe no catálogo → criada
    out = understat_into_catalog(db, lake)
    assert out == {"us_ligados": 2, "us_novos": 1, "us_promovidos": 2}
    m = db.get_match(3_000_000_001)
    assert m["data_level"] == DataLevel.BOXSCORE                       # deixou de ser "só placar"
    ts = db.load_boxscore(3_000_000_001)["team_stats"]
    xg = dict(zip(ts["team_name"], ts["value"]))
    assert xg == {"Arsenal FC": 1.8, "Chelsea FC": 0.6}                # nomes do catálogo, valores do Understat
    new = db.get_match(6_000_022_003)
    assert new and new["data_source"] == "understat" and new["data_level"] == DataLevel.BOXSCORE
    assert understat_id_for(3_000_000_001, lake) == 22001 and understat_id_for(6_000_022_003, lake) == 22003
    again = understat_into_catalog(db, lake)                           # rodar de novo não duplica
    assert again["us_novos"] == 0 and len(db.load_boxscore(3_000_000_001)["team_stats"]) == 2


def test_shots_are_fetched_once_on_demand(db, lake):
    from src.data_lake.understat_link import ensure_shots, understat_into_catalog

    db.upsert_matches([_m(3_000_000_001, "openfootball", DataLevel.RESULT, "Arsenal FC", "Chelsea FC")])
    _us(lake, [_row(22001, "Arsenal", "Chelsea")])
    understat_into_catalog(db, lake)
    calls = []

    class FakeProvider:
        def match_shots(self, uid):
            calls.append(uid)
            return [{"match_id": uid, "minute": 12, "h_a": "h", "h_team": "Arsenal", "a_team": "Chelsea", "player": "Saka",
                     "X": 0.9, "Y": 0.5, "xG": 0.31, "result": "Goal", "situation": "OpenPlay", "shotType": "LeftFoot"}]

        from src.data_hub.sources.understat import UnderstatProvider as _U
        shots_frame = staticmethod(_U.shots_frame)
    s1 = ensure_shots(3_000_000_001, lake=lake, provider=FakeProvider())
    s2 = ensure_shots(3_000_000_001, lake=lake, provider=FakeProvider())
    assert len(s1) == 1 and len(s2) == 1 and calls == [22001]          # baixou uma vez só
    assert ensure_shots(3_000_009_999, lake=lake, provider=FakeProvider()).empty   # sem ligação → nada


def test_espn_backfill_walks_months_and_downloads_summaries(db):
    from src.data_hub.sources.espn import EspnProvider

    p = EspnProvider(db, enabled=True)
    months, summaries = [], []

    def scoreboard(lg, d1, d2):
        months.append((lg, d1.isoformat(), d2.isoformat()))
        if d1.month == 5:
            return [{**_m(500_000_000 + 77, "espn", DataLevel.RESULT, "Flamengo", "Palmeiras", d="2024-05-12"),
                     "extra_json": '{"espn_league": "bra.1"}'}]
        return []

    def ingest(mid):
        summaries.append(mid)
        db.save_boxscore(mid, {"team_stats": [{"team_name": "Flamengo", "stat_key": "shots_total", "value": 15}],
                               "lineups": [], "timeline": []})
    p.scoreboard, p.ingest_event = scoreboard, ingest
    out = p.backfill(["bra.1"], since_year=2024, until=date(2024, 6, 30))
    assert [m[1] for m in months] == [f"2024-0{i}-01" for i in range(1, 7)]
    assert months[1][2] == "2024-02-29"                                 # fim de mês certo (bissexto)
    assert summaries == [500_000_077] and out["resumos"] == 1
    out2 = p.backfill(["bra.1"], since_year=2024, until=date(2024, 6, 30))
    assert out2["resumos"] == 0                                         # já tem números: não baixa de novo


def test_espn_backfill_stops_after_repeated_failures(db):
    from src.data_hub.sources.espn import EspnProvider

    p = EspnProvider(db, enabled=True)
    n = []

    def boom(*a):
        n.append(1)
        raise RuntimeError("HTTP 403")
    p.scoreboard = boom
    out = p.backfill(["bra.1"], since_year=2020, until=date(2024, 12, 31))
    assert len(n) == 5 and out["errors"] == 5                           # desiste com educação, não martela o site


def test_fdcouk_has_lower_divisions_and_full_history():
    from src.data_hub.sources.fdcouk import FIRST_SEASON, MAIN_LEAGUES

    assert {"E2", "E3", "EC", "SC1", "SC2", "SC3"} <= set(MAIN_LEAGUES) and FIRST_SEASON == 1993


def test_sync_cli_accepts_heavy_sources_only_on_request():
    from src.data_hub import sync

    assert "espn_historico" not in sync.ALL_SOURCES and "espn_historico" in sync.HEAVY_SOURCES
