"""Fontes abertas CC0: openfootball/football.json e resultados de seleções (martj42) — com trechos reais dos arquivos."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data_hub.db import DataHubDB
from src.data_hub.service import MatchDataService
from src.data_hub.sources.open_sources import OpenSourcesIngestor, load_config
from src.data_hub.sources.openfootball import OpenFootballProvider, minute, nice_name, split_name
from src.data_lake.lake import Lake

FX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=tmp_path / "hub.db", schema_path="database/schema.sql")


def test_helpers():
    assert nice_name("MOHAMED SALAH") == "Mohamed Salah" and nice_name("Virgil VAN DIJK") == "Virgil Van Dijk"
    assert minute("90+4") == (90, 4) and minute("37") == (37, None)
    assert split_name("England | Premier League 2025/26") == ("Premier League", "2025/26")
    assert split_name("Brasileiro Série A 2026") == ("Brasileiro Série A", "2026")


def test_openfootball_full_files_become_boxscores(db):
    p = OpenFootballProvider(db, local=FX / "openfootball")
    files = p.files(FX / "openfootball")
    assert any(f.name == "en.1-full.json" for f in files) and not any(f.name == "en.1.json" for f in files)
    out = p.sync(update=False)
    assert out["added"] == 5                       # 2 da Premier (a de 2099 não foi jogada) + 3 do Brasileirão
    cat = db.catalog("data_source = 'openfootball'")
    pl = cat[cat["competition_name"] == "Premier League"]
    assert set(pl["data_level"]) == {"BOXSCORE"} and set(pl["country_name"]) == {"England"}
    b = MatchDataService(db).load(int(pl.iloc[0]["match_id"]))
    tl = b.boxscore["timeline"]
    assert (tl["event_type"] == "Goal").sum() == int(pl.iloc[0]["home_score"] + pl.iloc[0]["away_score"])
    assert not b.boxscore["lineups"].empty


def test_open_sources_config_and_international_catalog(db, tmp_path):
    assert [f["id"] for f in load_config()][:3] == ["intl_resultados", "intl_gols", "intl_penaltis"]
    files = {"results.csv": FX / "ext" / "intl_results.csv", "goalscorers.csv": FX / "ext" / "intl_goalscorers.csv",
             "shootouts.csv": FX / "ext" / "intl_results.csv"}

    def fetch(url, headers):
        return 200, files[url.rsplit("/", 1)[-1]].read_bytes(), "e1"
    ing = OpenSourcesIngestor(cache=tmp_path / "c", fetch=fetch)
    lake = Lake(root=tmp_path / "lake", sqlite_path=tmp_path / "hub.db")
    out = ing.sync(lake, db=db)
    assert out["fontes"] == 3 and out["partidas_catalogo"] >= 2
    n1 = len(lake.read("os_intl_resultados"))
    again = OpenSourcesIngestor(cache=tmp_path / "c", fetch=fetch).sync(lake, db=db)
    assert again["errors"] == 0 and len(lake.read("os_intl_resultados")) == n1      # sem duplicar linhas
    final = db.catalog("data_source = 'intl' AND home_team_name = 'Argentina' AND away_team_name = 'France'")
    assert len(final) == 1 and final.iloc[0]["data_level"] == "BOXSCORE"
    box = MatchDataService(db).load(int(final.iloc[0]["match_id"])).boxscore["timeline"]
    assert "Lionel Messi" in set(box["player_name"])
    r = MatchDataService(db).finder.find("Brasil x Inglaterra 1970", allow_remote=False)
    assert not r["candidates"].empty


# ---------------------------------------------------------------- chat único e escudos
def _catalog():
    import pandas as pd

    return pd.DataFrame([
        {"match_id": 1, "home_team_name": "Argentina", "away_team_name": "France", "match_date": "2022-12-18", "home_score": 3,
         "away_score": 3, "competition_name": "FIFA World Cup", "data_level": "EVENTS", "data_source": "statsbomb", "round_name": "Final"},
        {"match_id": 2, "home_team_name": "Argentina", "away_team_name": "France", "match_date": "2022-12-18", "home_score": 3,
         "away_score": 3, "competition_name": "FIFA World Cup", "data_level": "BOXSCORE", "data_source": "intl", "round_name": ""},
        {"match_id": 3, "home_team_name": "Brazil", "away_team_name": "England", "match_date": "1970-06-07", "home_score": 1,
         "away_score": 0, "competition_name": "FIFA World Cup", "data_level": "RESULT", "data_source": "intl", "round_name": ""},
        {"match_id": 4, "home_team_name": "Bayer Leverkusen", "away_team_name": "Augsburg", "match_date": "2024-05-18", "home_score": 2,
         "away_score": 1, "competition_name": "1. Bundesliga", "data_level": "EVENTS", "data_source": "statsbomb", "round_name": ""},
        {"match_id": 5, "home_team_name": "Werder Bremen", "away_team_name": "Bayer Leverkusen", "match_date": "2024-04-14", "home_score": 0,
         "away_score": 5, "competition_name": "1. Bundesliga", "data_level": "EVENTS", "data_source": "statsbomb", "round_name": ""},
    ])


def test_match_locator_reads_match_inside_question():
    from src.intelligence.match_locator import locate

    c = _catalog()
    assert locate("Na final da Copa de 2022, como a Argentina pressionou a França?", c).match_id == 1   # prefere eventos
    assert locate("o que o brasil fez para ganhar da inglaterra em 1970?", c).match_id == 3
    assert locate("quem fez gol no último jogo do Leverkusen?", c).match_id == 4
    assert locate("como foi a transição defensiva depois do minuto 60?", c) is None
    assert locate("o Leverkusen joga bem?", c) is None          # um time só, sem dizer qual jogo


def test_crests_flags_and_monogram():
    from src.ui.crests import crest_img, crest_url, monogram, nation_code

    assert nation_code("Brazil") == "br" and nation_code("England") == "gb-eng" and nation_code("Brazil Women") == "br"
    assert crest_url("Argentina").endswith("/ar.png")
    m = monogram("Clube Atlético Mineiro")
    assert m.startswith("data:image/svg+xml;base64,") and monogram("Clube Atlético Mineiro") == m
    assert "onerror" in crest_img("Time Inexistente FC")
