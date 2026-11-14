"""v27: validação de domínio, duplicatas SHA-256, parsers com amostras, identidades com confiança, ligação e DuckDB."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.data_hub import quality as q
from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel

FX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")


def _m(mid, **k):
    r = {"match_id": mid, "home_team_name": "Arsenal", "away_team_name": "Chelsea", "match_date": "2024-03-10",
         "home_score": 2, "away_score": 1, "competition_name": "Premier League", "season_name": "2023/24",
         "status": "FT", "data_source": "fdcouk", "data_level": DataLevel.BOXSCORE}
    r.update(k)
    return r


# ------------------------------------------------------------------ domínio
@pytest.mark.parametrize("bad,motivo", [
    (dict(home_score=-1), "negativo"), (dict(away_score=1.5), "inteiro"), (dict(home_team_name=""), "ausente"),
    (dict(away_team_name="arsenal"), "igual"), (dict(match_date="2024-02-30"), "data inválida"),
    (dict(match_date="1850-01-01", season_name=""), "1870"), (dict(match_date="2099-01-01", season_name=""), "futura"),
])
def test_check_match_blocks_impossible_values(bad, motivo):
    errors, _ = q.check_match(_m(1, **bad), today=date(2026, 11, 14))
    assert any(motivo in e for e in errors), errors


def test_season_coherence_is_a_warning_not_a_block():
    assert q.season_window("2023/24") == (date(2023, 6, 1), date(2024, 7, 31))
    assert q.season_window("2023/2024") == (date(2023, 6, 1), date(2024, 7, 31))
    assert q.season_window("2026") == (date(2026, 1, 1), date(2027, 7, 31))
    e, w = q.check_match(_m(1, match_date="2022-01-10"), today=date(2026, 1, 1))
    assert e == [] and "fora da temporada" in w[0]


def test_upsert_rejects_invalid_rows_but_keeps_valid(db, tmp_path, monkeypatch):
    from src.data_hub import net

    monkeypatch.setattr(net, "LOG_FILE", tmp_path / "log.txt")
    r = db.upsert_matches([_m(2_000_000_001), _m(2_000_000_002, home_score=-3)])
    assert r["added"] == 1 and r["rejected"] == 1
    assert db.get_match(2_000_000_002) is None
    assert "rejeitada" in (tmp_path / "log.txt").read_text(encoding="utf-8")


def test_events_and_timeline_ranges(db):
    ev = pd.DataFrame({"minute": [0, 45, 131, -1], "x": [60, 121, 10, 10], "y": [40, 40, 81, 40],
                       "end_x": [None, 50, 50, 50], "end_y": [None, 40, 40, 40]})
    bad = q.validate_events(ev)
    assert set(bad["index"]) == {1, 2, 3}
    assert "x fora" in bad.set_index("index").loc[1, "problema"]
    db.upsert_matches([_m(2_000_000_005)])
    db.save_boxscore(2_000_000_005, {"team_stats": [], "lineups": [], "timeline": [
        {"minute": 12, "team_name": "Arsenal", "player_name": "Saka", "event_type": "Goal"},
        {"minute": 400, "team_name": "Arsenal", "player_name": "X", "event_type": "Goal"}]})
    assert len(db.load_boxscore(2_000_000_005)["timeline"]) == 1


# --------------------------------------------------------------- duplicatas
def test_sha256_duplicates_vs_cross_source_links():
    cat = pd.DataFrame([
        _m(1, data_source="fdcouk", home_team_name="Man United", away_team_name="Fulham"),
        _m(2, data_source="fdcouk", home_team_name="Manchester United FC", away_team_name="Fulham FC"),   # duplicata
        _m(3, data_source="openfootball", home_team_name="Manchester United", away_team_name="Fulham"),  # ligação
        _m(4, data_source="fdcouk", home_team_name="Man United", away_team_name="Fulham", away_score=2),  # outro jogo
    ])
    h = q.content_hash(cat.iloc[0].to_dict())
    assert len(h) == 64 and h == q.content_hash(cat.iloc[1].to_dict())
    d = q.find_duplicates(cat)
    assert set(d.loc[d["tipo"] == "duplicata", "match_id"]) == {1, 2}
    assert set(d.loc[d["tipo"] != "duplicata", "match_id"]) == {3}
    assert 4 not in set(d["match_id"])


def test_quality_audit_on_db(db):
    db.upsert_matches([_m(2_000_000_011), _m(2_000_000_012, home_team_name="Arsenal FC", away_team_name="Chelsea FC")])
    a = q.audit(db)
    assert len(a["duplicatas"]) == 2 and a["lances_fora"] == 0


# ------------------------------------------------------------------ parsers
def test_fdcouk_csv_with_missing_columns_still_parses():
    from src.data_hub.sources.fdcouk import FootballDataCoUkProvider as P

    full = pd.read_csv(FX / "fdcouk" / "E0.csv")
    slim = full.drop(columns=["HST", "AST", "HC", "AC", "Referee", "HTHG", "HTAG"])
    out = P.parse_main(slim, "E0", 2024)
    assert len(out) == len(full.dropna(subset=["HomeTeam"]))
    rec, box = out[0]
    keys = {s["stat_key"] for s in box["team_stats"]}
    assert "shots_total" in keys and "shots_on_target" not in keys and "corners" not in keys
    assert rec["data_level"] == DataLevel.BOXSCORE and rec["referee_name"] == ""
    only_score = full[["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]]
    rec2, box2 = P.parse_main(only_score, "E0", 2024)[0]
    assert box2["team_stats"] == [] and rec2["data_level"] == DataLevel.RESULT       # sem números = só placar


def test_fdcouk_full_sample_reads_shots_on_target_and_corners():
    from src.data_hub.sources.fdcouk import FootballDataCoUkProvider as P

    rec, box = P.parse_main(pd.read_csv(FX / "fdcouk" / "E0.csv"), "E0", 2024)[0]
    st = {(s["team_name"], s["stat_key"]): s["value"] for s in box["team_stats"]}
    assert st[("Man United", "shots_on_target")] == 5 and st[("Fulham", "corners")] == 8


def test_parsers_on_samples_produce_valid_matches():
    import json

    from src.data_hub.sources.api_football import ApiFootballProvider
    from src.data_hub.sources.espn import EspnProvider

    rec, box = ApiFootballProvider.parse_fixture(
        json.loads((FX / "api_football_fixture.json").read_text(encoding="utf-8"))["response"][0])
    assert q.check_match(rec)[0] == [] and box["team_stats"]
    summ = json.loads((FX / "espn_summary.json").read_text(encoding="utf-8"))
    rec, box = EspnProvider.parse_summary(summ, "bra.1", 1)
    assert q.check_match(rec)[0] == []
    assert all(0 <= (e["minute"] or 0) <= q.MINUTE_MAX for e in box["timeline"])


# --------------------------------------------------------------- identidades
def test_team_identity_confidence_and_review_flag():
    from src.data_lake.ids import REVIEW_BELOW, resolve_teams

    dim, ids = resolve_teams([
        {"fonte": "fdcouk", "id_fonte": "", "nome": "Man United", "pais": "England"},
        {"fonte": "statsbomb", "id_fonte": "39", "nome": "Manchester United", "pais": "England"},
        {"fonte": "espn", "id_fonte": "360", "nome": "Manchester Utd", "pais": "England"},
        {"fonte": "espn", "id_fonte": "1", "nome": "Wolverhampton Wanderers", "pais": "England"},
        {"fonte": "fdcouk", "id_fonte": "", "nome": "Wolves", "pais": "England"},
    ])
    mu = ids[ids["nome"].isin(["Man United", "Manchester United"])]
    assert mu["team_key"].nunique() == 1 and (mu["confianca"] == 1.0).all()
    assert ids["confianca"].between(0, 1).all() and "revisar" in ids
    assert (ids["revisar"] == (ids["confianca"] < REVIEW_BELOW)).all()
    assert "confianca_min" in dim


def test_player_identity_confidence_levels():
    from src.data_lake.ids import resolve_players

    dim, ids = resolve_players([
        {"fonte": "transfermarkt", "id_fonte": "28003", "nome": "Lionel Messi", "team_key": "inter-miami", "nascimento": "1987-06-24"},
        {"fonte": "statsbomb", "id_fonte": "5503", "nome": "Lionel Andrés Messi Cuccittini", "team_key": "inter-miami"},
        {"fonte": "understat", "id_fonte": "2097", "nome": "Lionel Messi", "team_key": "inter-miami"},
        {"fonte": "espn", "id_fonte": "9", "nome": "Fulano Sem Clube", "team_key": ""},
    ])
    c = ids.set_index("fonte")["confianca"]
    assert c["transfermarkt"] == 1.0 and c["understat"] == 0.9 and c["statsbomb"] == 0.8 and c["espn"] == 0.6
    assert ids.loc[ids["fonte"] != "espn", "player_key"].nunique() == 1
    assert bool(ids.set_index("fonte").loc["espn", "revisar"]) is True


# ------------------------------------------------------- ligação entre bases
def test_match_linking_between_sources(db):
    from src.data_hub.service import MatchDataService

    db.upsert_matches([_m(3_000_000_001, data_source="openfootball", data_level=DataLevel.RESULT,
                          home_team_name="Arsenal FC", away_team_name="Chelsea FC"),
                       _m(2_000_000_001), _m(2_000_000_009, home_team_name="Everton")])
    sib = MatchDataService(db).stats_sibling(3_000_000_001, db.get_match(3_000_000_001))
    db.save_boxscore(2_000_000_001, {"team_stats": [{"team_name": "Arsenal", "stat_key": "shots_total", "value": 1}],
                                     "lineups": [], "timeline": []})
    sib = MatchDataService(db).stats_sibling(3_000_000_001, db.get_match(3_000_000_001))
    assert sib is not None and sib["match_id"] == 2_000_000_001          # o jogo do Everton não confunde


# ------------------------------------------------------------------- DuckDB
def test_lake_sql_portable_name_on_sqlite_mirror(tmp_path, monkeypatch):
    import src.data_lake.lake as L

    monkeypatch.setattr(L, "HAS_DUCKDB", False)
    lake = L.Lake(root=tmp_path / "lake", sqlite_path=tmp_path / "hub.db")
    lake.write("dim_teams", pd.DataFrame({"team_key": ["a", "b"], "nome": ["A", "B"]}), source="t", connector="t")
    assert lake.sql("SELECT COUNT(*) AS n FROM lake_dim_teams").iloc[0]["n"] == 2


def test_lake_duckdb_pipeline(tmp_path):
    pytest.importorskip("duckdb")
    import src.data_lake.lake as L

    lake = L.Lake(root=tmp_path / "lake", sqlite_path=tmp_path / "hub.db")
    lake.write("dim_teams", pd.DataFrame({"team_key": ["a", "b", "c"], "nome": ["A", "B", "C"]}), source="t", connector="t")
    assert lake.sql("SELECT COUNT(*) AS n FROM dim_teams").iloc[0]["n"] == 3
    assert lake.sql("SELECT COUNT(*) AS n FROM lake_dim_teams").iloc[0]["n"] == 3


# ------------------------------------------------------------- desempenho
def test_search_on_66k_matches_is_fast(tmp_path):
    """Meta do projeto: < 1 s por busca numa base de 66 mil jogos (aqui com folga para máquinas lentas)."""
    import random
    import time

    from src.data_hub.service import MatchDataService

    db = DataHubDB(db_path=str(tmp_path / "big.db"), schema_path="database/schema.sql")
    rng = random.Random(1)
    teams = [f"Clube {i}" for i in range(600)] + ["Bayer Leverkusen", "Flamengo", "Palmeiras", "Brazil", "Croatia"]
    recs = []
    for i in range(66_000):
        h, a = rng.sample(teams, 2)
        recs.append({"match_id": 2_000_000_000 + i, "home_team_name": h, "away_team_name": a,
                     "match_date": f"{rng.randint(1995, 2025)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                     "home_score": rng.randint(0, 4), "away_score": rng.randint(0, 4), "competition_name": f"Liga {i % 16}",
                     "season_name": "", "status": "FT", "data_source": "fdcouk", "data_level": DataLevel.RESULT})
    db.upsert_matches(recs)
    svc = MatchDataService(db)
    svc.finder.find("aquecimento", allow_remote=False)
    worst = 0.0
    for q in ("Flamengo x Palmeiras", "Leverkusen", "Clube 17 x Clube 300", "Brazil x Croatia 2018"):
        t = time.time()
        svc.finder.find(q, allow_remote=False)
        worst = max(worst, time.time() - t)
    assert worst < 2.0, f"busca levou {worst:.2f}s"
