"""
Dia 20 — ecossistema multi-fonte: Transfermarkt (transfermarkt-datasets), Understat, API-Futebol, API-Football
(classificação/calendário), StatsBomb local, lake (Parquet/CSV + espelho SQLite) e mapeamento de IDs.
Tudo com amostras no formato publicado por cada fonte (sem rede).
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

from src.data_hub.db import DataHubDB
from src.data_lake.build import build_all, market_values, shots_for_match
from src.data_lake.ids import resolve_players, resolve_teams, team_core
from src.data_lake.lake import Lake

FX = Path(__file__).parent / "fixtures" / "ext"


@pytest.fixture()
def env(tmp_path):
    db = DataHubDB(db_path=tmp_path / "hub.db", schema_path="database/schema.sql")
    db.upsert_matches([{"match_id": 2_000_000_123, "data_source": "fdcouk", "data_level": "BOXSCORE",
                        "competition_name": "Premier League", "season_name": "2024/2025", "match_date": "2024-08-16",
                        "home_team_name": "Man United", "away_team_name": "Fulham", "home_score": 1, "away_score": 0,
                        "country_name": "England"}])
    lake = Lake(root=tmp_path / "lake", sqlite_path=tmp_path / "hub.db")
    return db, lake, tmp_path


def _transfermarkt(lake, tmp_path):
    from src.data_hub.sources.transfermarkt_ds import TransfermarktDatasets

    cache = tmp_path / "tm"
    cache.mkdir()
    for f in FX.glob("tm_*.csv.gz"):
        shutil.copy(f, cache / f.name.replace("tm_", ""))
        os.utime(cache / f.name.replace("tm_", ""), None)
    return TransfermarktDatasets(cache_dir=cache).sync(lake)


def _understat(lake, tmp_path, monkeypatch):
    import src.data_hub.sources.understat as us

    cache = tmp_path / "us"
    cache.mkdir()
    shutil.copy(FX / "understat_league.json", cache / "getLeagueData_EPL_2024.txt")
    shutil.copy(FX / "understat_match.json", cache / "getMatchData_26602.txt")
    monkeypatch.setattr(us, "season_start", lambda today=None: 2024)
    return us.UnderstatProvider(cache_dir=cache).sync(lake, leagues=["EPL"])


def test_team_core_and_resolution():
    assert team_core("Man United") == team_core("Manchester United FC") == "manchester united"
    assert team_core("Atlético-MG") == team_core("Clube Atlético Mineiro")
    dims, ids = resolve_teams([
        {"fonte": "fdcouk", "id_fonte": "", "nome": "Ath Madrid", "pais": "Spain"},
        {"fonte": "statsbomb", "id_fonte": "212", "nome": "Atlético Madrid", "pais": "Spain"},
        {"fonte": "statsbomb", "id_fonte": "220", "nome": "Real Madrid", "pais": "Spain"},
    ])
    am = dims[dims["team_key"] == "atletico-madrid"].iloc[0]
    assert am["n_fontes"] == 2 and am["statsbomb_id"] == "212"
    assert len(dims) == 2                                   # Real Madrid não é fundido com o Atlético


def test_player_resolution_full_and_short_names():
    dims, _ = resolve_players([
        {"fonte": "transfermarkt", "id_fonte": "28003", "nome": "Lionel Messi", "team_key": "inter-miami", "nascimento": "1987-06-24"},
        {"fonte": "statsbomb", "id_fonte": "5503", "nome": "Lionel Andrés Messi Cuccittini", "team_key": "inter-miami"},
        {"fonte": "understat", "id_fonte": "2097", "nome": "Lionel Messi", "team_key": "inter-miami"},
    ])
    assert len(dims) == 1 and dims.iloc[0]["n_fontes"] == 3 and dims.iloc[0]["nascimento"] == "1987-06-24"


def test_lake_write_read_upsert_and_mirror(env):
    db, lake, _ = env
    lake.write("t", pd.DataFrame({"k": [1, 2], "v": ["a", "b"]}), source="teste")
    lake.upsert("t", pd.DataFrame({"k": [2, 3], "v": ["B", "c"]}), ["k"])
    t = lake.read("t").sort_values("k")
    assert t["v"].tolist() == ["a", "B", "c"] and "ingestao_utc" in t
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM lake_t").fetchone()[0] == 3
    assert "t" in set(lake.tables()["tabela"])


def test_understat_parsers_new_and_embedded_formats():
    from src.data_hub.sources.understat import UnderstatProvider as U, _embedded

    lg = json.loads((FX / "understat_league.json").read_text())
    m = U.matches_frame(lg["dates"], "EPL", 2024)
    assert len(m) == 1 and m.iloc[0]["xg_mandante"] == 2.42          # só partidas encerradas
    shots = U.shots_frame(json.loads((FX / "understat_match.json").read_text())["shots"]["h"])
    assert shots.iloc[0]["resultado"] == "gol" and 0 < shots.iloc[0]["x"] <= 120
    old = _embedded((FX / "understat_match_old.html").read_text(), "shotsData")
    assert old["h"][0]["player"] == "Joshua Zirkzee"


def test_end_to_end_links_shots_and_market_values(env, monkeypatch):
    db, lake, tmp = env
    _transfermarkt(lake, tmp)
    r = _understat(lake, tmp, monkeypatch)
    assert r["partidas"] == 1 and r["finalizacoes"] == 2
    out = build_all(db, lake)
    dt = lake.read("dim_teams")
    mu = dt[dt["team_key"] == "manchester-united"].iloc[0]
    assert mu["transfermarkt_id"] == "985" and mu["understat_id"] == "89" and mu["n_fontes"] >= 3
    assert out["links"] >= 2                                           # catálogo ↔ Understat e ↔ Transfermarkt
    sh = shots_for_match(2_000_000_123, lake)
    assert len(sh) == 2 and set(sh["equipe"]) == {"Manchester United", "Fulham"}
    dp = lake.read("dim_players")
    bruno = dp[dp["nome"] == "Bruno Fernandes"].iloc[0]
    assert bruno["transfermarkt_id"] == "240306" and bruno["understat_id"] == "1228" and bruno["nascimento"] == "1994-09-08"
    mv = market_values(lake)
    assert (mv[mv["fonte"] == "understat"]["valor_mercado_eur"] == 40_000_000).any()


def test_api_futebol_and_api_football_tables():
    from src.data_hub.sources.api_football import standings_frame
    from src.data_hub.sources.api_futebol import ApiFutebolProvider as A

    t = A.standings_frame(json.loads((FX / "api_futebol_tabela.json").read_text()), "Brasileirão", "2026")
    assert t.iloc[0]["equipe"] == "Palmeiras" and t.iloc[0]["ultimos_jogos"] == "vvevd"
    p = A.matches_frame(json.loads((FX / "api_futebol_partidas.json").read_text()), "Brasileirão")
    assert p.iloc[0]["data"] == "2026-11-07" and p.iloc[0]["gols_mandante"] == 2
    s = standings_frame(json.loads((FX / "api_football_standings.json").read_text()), "Brasileirão Série A")
    assert s.iloc[0]["pontos"] == 73 and s.iloc[0]["api_football_id"] == 121
    assert A(api_key="").enabled is False


def test_statsbomb_local_clone(tmp_path, monkeypatch):
    import src.data_hub.sources.statsbomb as sb

    root = tmp_path / "open-data" / "data"
    (root / "events").mkdir(parents=True)
    (root / "competitions.json").write_text("[]")
    (root / "events" / "123.json").write_text(json.dumps([{"id": "x"}]))
    monkeypatch.setenv("STATSBOMB_OPEN_DATA_PATH", str(tmp_path / "open-data"))
    assert sb.local_root() == root
    assert sb._read_local("events/123.json") == [{"id": "x"}] and sb._read_local("events/999.json") is None


def test_basedosdados_disabled_without_billing(monkeypatch):
    from src.data_hub.sources.basedosdados import BaseDosDadosProvider as B

    monkeypatch.delenv("BASEDOSDADOS_BILLING_ID", raising=False)
    assert B().enabled is False
    n = B.normalize(pd.DataFrame({"ano_campeonato": [2003], "publico": [30000], "time_mandante": ["Cruzeiro"],
                                  "data": ["2003-03-30"]}))
    assert {"temporada", "publico", "mandante"} <= set(n.columns)
