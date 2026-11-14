"""v29: bases públicas montadas pela comunidade — Brasileirão (Adão Duque), open-matchday, súmulas da CBF, OpenPlay
e a consolidação por precedência com registro de divergências."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel, source_from_internal_id


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")


# --------------------------------------------------------------- Brasileirão
LEGENDA = {  # cabeçalhos como na Legenda.txt do repositório
    "partidas": "ID,Rodada,Data,Horário,Dia,Mandante,Visitante,formacao_mandante,formacao_visitante,tecnico_mandante,"
                "tecnico_visitante,Vencedor,Arena,mandante_Placar,visitante_Placar,mandante_Estado,visitante_Estado\n"
                "8001,1,29/03/2003,16:00,Sábado,Guarani,Vasco,,,,,-,Brinco de Ouro,4,2,SP,RJ\n"
                "8500,10,15/06/2024,18:30,Sábado,Flamengo,Palmeiras,4-3-3,4-4-2,Tite,Abel Ferreira,Flamengo,Maracanã,2,1,RJ,SP\n",
    "estatisticas": "partida_ID,Rodada,Clube,Chutes,Chutes a gol,Posse de bola,Passes,precisao_passes,Faltas,"
                    "cartao_amarelo,cartao_vermelho,Impedimentos,Escanteios\n"
                    "8001,1,Guarani,0,0,,0,,0,0,0,0,0\n8001,1,Vasco,0,0,,0,,0,0,0,0,0\n"
                    "8500,10,Flamengo,15,6,58%,512,87%,11,2,0,1,7\n8500,10,Palmeiras,9,3,42%,371,81%,14,3,1,2,4\n",
    "gols": "partida_ID,Rodada,Clube,Atleta,Minuto\n8500,10,Flamengo,Pedro,23\n8500,10,Palmeiras,Estêvão,45+2\n"
            "8500,10,Flamengo,Arrascaeta,78\n",
    "cartoes": "partida_ID,Rodada,Clube,Cartao,Atleta,num_camisa,Posicao,Minuto\n8500,10,Palmeiras,Vermelho,Gómez,15,Zagueiro,88\n",
}
LOWER = {  # mesma base com os cabeçalhos em minúsculas (variação que também circula)
    "partidas": LEGENDA["partidas"].replace("ID,Rodada,Data", "ID,rodata,data").replace("Mandante,Visitante", "mandante,visitante"),
    "estatisticas": LEGENDA["estatisticas"].replace("Chutes a gol", "chutes_no_alvo").replace("Posse de bola", "posse_de_bola"),
    "gols": LEGENDA["gols"], "cartoes": LEGENDA["cartoes"],
}


@pytest.mark.parametrize("files", [LEGENDA, LOWER])
def test_brasileirao_dataset_both_header_styles(db, tmp_path, files):
    from src.data_hub.sources.brasileirao_dataset import FILES, BrasileiraoDatasetProvider

    for k, name in FILES.items():
        (tmp_path / name).write_text(files[k], encoding="utf-8")
    out = BrasileiraoDatasetProvider(db, local=str(tmp_path)).sync()
    assert out["partidas"] == 2 and out["com_estatisticas"] == 1
    m = db.get_match(7_000_008_500)
    assert m["match_date"] == "2024-06-15" and m["data_level"] == DataLevel.BOXSCORE and m["stadium_name"] == "Maracanã"
    assert m["round_name"] == "Rodada 10" and source_from_internal_id(7_000_008_500) == "brasileirao"
    box = db.load_boxscore(7_000_008_500)
    st = {(r.team_name, r.stat_key): r.value for r in box["team_stats"].itertuples()}
    assert st[("Flamengo", "possession_pct")] == 58 and st[("Palmeiras", "shots_on_target")] == 3
    assert st[("Flamengo", "pass_accuracy_pct")] == 87 and st[("Palmeiras", "red_cards")] == 1
    tl = box["timeline"]
    assert len(tl) == 4 and set(tl["player_name"]) >= {"Pedro", "Estêvão", "Gómez"}
    assert int(tl.loc[tl["player_name"] == "Estêvão", "extra_minute"].iloc[0]) == 2
    assert db.get_match(7_000_008_001)["data_level"] == DataLevel.RESULT          # estatística toda zerada = sem número


def test_brasileirao_stats_reach_score_only_sibling(db, tmp_path):
    from src.data_hub.service import MatchDataService
    from src.data_hub.sources.brasileirao_dataset import FILES, BrasileiraoDatasetProvider

    for k, name in FILES.items():
        (tmp_path / name).write_text(LEGENDA[k], encoding="utf-8")
    BrasileiraoDatasetProvider(db, local=str(tmp_path)).sync()
    db.upsert_matches([{"match_id": 3_000_000_777, "home_team_name": "CR Flamengo", "away_team_name": "SE Palmeiras",
                        "match_date": "2024-06-15", "home_score": 2, "away_score": 1, "competition_name": "Brasileirão",
                        "season_name": "2024", "status": "FT", "data_source": "openfootball", "data_level": DataLevel.RESULT}])
    b = MatchDataService(db).load(3_000_000_777)
    assert b.level == DataLevel.BOXSCORE and any("brasileirao" in n for n in b.notes)


# --------------------------------------------------------------- open-matchday
RESULTS = ("gw,date,time,home,away,ft_home,ft_away,ft_result,ht_home,ht_away,ht_result,home_shots,away_shots,"
           "home_shots_on_target,away_shots_on_target,home_fouls,away_fouls,home_corners,away_corners,home_yellow,"
           "away_yellow,home_red,away_red,goal_minutes,source\n"
           "11,2026-11-07,15:00,Arsenal,Chelsea,2,1,H,1,0,H,17,8,7,3,9,12,8,2,1,3,0,0,\"12,61,88\",espn+fdcouk\n"
           "11,2026-11-08,17:30,Everton,Fulham,0,0,D,0,0,D,,,,,,,,,,,,,,espn\n")
GOALS = ("gw,date,home,away,minute,score_home,score_away,scorer\n11,2026-11-07,Arsenal,Chelsea,12,1,0,Saka\n"
         "11,2026-11-07,Arsenal,Chelsea,61,1,1,Palmer\n11,2026-11-07,Arsenal,Chelsea,88,2,1,Ødegaard\n")
FIXTURES = "gw,date,time,home,away\n12,2099-11-21,15:00,Chelsea,Arsenal\n"


def test_open_matchday_results_goals_and_agenda(db, tmp_path, monkeypatch):
    import src.data_hub.sources.open_matchday as OM
    import src.data_lake.lake as L

    monkeypatch.setattr(OM, "CACHE", tmp_path / "c")
    monkeypatch.setattr(L, "HAS_DUCKDB", False)
    lake = L.Lake(root=tmp_path / "lake", sqlite_path=tmp_path / "hub.db")
    files = {"results": RESULTS, "goals": GOALS, "fixtures": FIXTURES}
    fetch = lambda url: files[url.rsplit("/", 1)[1].split("_")[0]].encode() if "ENG_1" in url else b""
    out = OM.OpenMatchdayProvider(db, fetch=fetch).sync(lake, folders=["ENG_1_premier-league", "XXX_9_nada"])
    assert out["competicoes"] == 1 and out["agenda"] == 1
    cat = db.catalog("data_source = 'open_matchday'")
    ars = cat[cat["home_team_name"] == "Arsenal"].iloc[0]
    assert ars["data_level"] == DataLevel.BOXSCORE and ars["season_name"] == f"20{OM.season_code()[:2]}/20{OM.season_code()[2:]}"
    assert cat[cat["home_team_name"] == "Everton"].iloc[0]["data_level"] == DataLevel.RESULT
    box = db.load_boxscore(int(ars["match_id"]))
    st = {(r.team_name, r.stat_key): r.value for r in box["team_stats"].itertuples()}
    assert st[("Arsenal", "shots_on_target")] == 7 and st[("Chelsea", "corners")] == 2 and st[("Arsenal", "ht_goals")] == 1
    tl = box["timeline"]
    assert list(tl["player_name"]) == ["Saka", "Palmer", "Ødegaard"] and list(tl["team_name"]) == ["Arsenal", "Chelsea", "Arsenal"]
    ag = lake.read("agenda")
    assert ag.iloc[0]["mandante"] == "Chelsea" and ag.iloc[0]["competicao"] == "Premier League"
    again = OM.OpenMatchdayProvider(db, fetch=fetch).sync(lake, folders=["ENG_1_premier-league"])
    assert again["added"] == 0                                                   # id estável: não duplica


# --------------------------------------------------------------- súmulas CBF
def test_cbf_sumulas_heuristic_reader(db, tmp_path):
    from src.data_hub.sources.cbf_sumulas import CbfSumulasProvider, inspect

    base = tmp_path / "cbf" / "results" / "serie_c" / "2024"
    base.mkdir(parents=True)
    (base / "jogo_001.json").write_text(json.dumps({
        "mandante": {"nome": "Remo"}, "visitante": {"nome": "Paysandu"}, "gols_mandante": 2, "gols_visitante": 2,
        "data": "05/05/2024", "estadio": "Baenão", "arbitro": "Fulano de Tal",
        "gols": [{"atleta": "Ytalo", "minuto": "10", "clube": "Remo"}, {"atleta": "Nicolas", "minuto": "90+3", "clube": "Paysandu"}],
        "cartoes": [{"atleta": "Bryan", "minuto": "55", "clube": "Remo", "tipo": "Amarelo"}]}), encoding="utf-8")
    (base / "outros.csv").write_text("coluna_x,coluna_y\n1,2\n", encoding="utf-8")
    p = CbfSumulasProvider(db, path=str(tmp_path / "cbf"))
    out = p.sync()
    assert out["partidas"] == 1 and out["nao_reconhecidos"] == 1
    m = db.catalog("data_source = 'cbf'").iloc[0]
    assert m["competition_name"] == "Campeonato Brasileiro Série C" and m["season_name"] == "2024"
    assert m["data_level"] == DataLevel.RESULT and m["stadium_name"] == "Baenão" and m["referee_name"] == "Fulano de Tal"
    tl = db.load_boxscore(int(m["match_id"]))["timeline"]
    assert len(tl) == 3 and set(tl["event_type"]) == {"Goal", "Card"}
    rep = inspect(str(tmp_path / "cbf"))
    assert "reconhecido" in rep and "NÃO reconhecido" in rep


# --------------------------------------------------------------- OpenPlay
def test_openplay_catalog_and_events_conversion(db, tmp_path):
    from src.data_hub.service import MatchDataService
    from src.data_hub.sources.openplay import OpenPlayProvider, inspect

    d = tmp_path / "op"
    d.mkdir()
    pd.DataFrame([{"match_id": 1711, "date": "2023-08-12T14:00:00Z", "home_team": "Arsenal", "away_team": "Nottingham Forest",
                   "home_score": 2, "away_score": 1, "competition": "Premier League", "season": "2023/2024"}]
                 ).to_csv(d / "matches.csv", index=False)
    pd.DataFrame([{"match_id": 1711, "team": "Arsenal", "corners_taken": 8, "yellow_cards": 1, "red_cards": 0},
                  {"match_id": 1711, "team": "Nottingham Forest", "corners_taken": 2, "yellow_cards": 3, "red_cards": 0}]
                 ).to_csv(d / "team_match_stats.csv", index=False)
    ev = [  # formato WhoScored/Opta: coordenadas 0–100
        {"match_id": 1711, "period": "FirstHalf", "minute": 1, "second": 5, "team": "Arsenal", "player": "Rice",
         "type": "Pass", "outcome_type": "Successful", "x": 50, "y": 50, "end_x": 70, "end_y": 30},
        {"match_id": 1711, "period": "FirstHalf", "minute": 1, "second": 8, "team": "Arsenal", "player": "Saka",
         "type": "Pass", "outcome_type": "Unsuccessful", "x": 70, "y": 30, "end_x": 85, "end_y": 50},
        {"match_id": 1711, "period": "FirstHalf", "minute": 2, "second": 0, "team": "Nottingham Forest", "player": "Gibbs-White",
         "type": "BallRecovery", "outcome_type": "Successful", "x": 20, "y": 40},
        {"match_id": 1711, "period": "FirstHalf", "minute": 26, "second": 0, "team": "Arsenal", "player": "Nketiah",
         "type": "Goal", "outcome_type": "Successful", "x": 90, "y": 52, "xg": 0.41},
        {"match_id": 1711, "period": "SecondHalf", "minute": 60, "second": 0, "team": "Arsenal", "player": "Saka",
         "type": "SavedShot", "outcome_type": "Successful", "x": 85, "y": 70, "xg": 0.08},
        {"match_id": 1711, "period": "SecondHalf", "minute": 61, "second": 0, "team": "Arsenal", "player": "Saka",
         "type": "FormationChange", "x": 0, "y": 0},
        {"match_id": 9999, "period": "FirstHalf", "minute": 1, "team": "X", "player": "Y", "type": "Pass", "x": 1, "y": 1}]
    pd.DataFrame(ev).to_csv(d / "events.csv", index=False)
    p = OpenPlayProvider(db, path=str(d))
    assert set(p.files()) == {"matches", "events", "team_match_stats"}
    assert p.sync()["partidas"] == 1
    m = db.catalog("data_source = 'openplay'").iloc[0]
    mid = int(m["match_id"])
    assert m["data_level"] == DataLevel.EVENTS and source_from_internal_id(mid) == "openplay" and m["match_date"] == "2023-08-12"
    ts = db.load_boxscore(mid)["team_stats"]
    assert dict(zip(ts.loc[ts["stat_key"] == "corners", "team_name"], ts.loc[ts["stat_key"] == "corners", "value"])) == \
        {"Arsenal": 8, "Nottingham Forest": 2}
    svc = MatchDataService(db)
    svc.openplay_path = str(d)
    import os

    os.environ["OPENPLAY_PATH"] = str(d)
    try:
        b = svc.load(mid)
    finally:
        os.environ.pop("OPENPLAY_PATH", None)
    e = b.events
    assert b.level == DataLevel.EVENTS and len(e) == 5                       # FormationChange e o outro jogo ficam fora
    assert list(e["type_name"]) == ["Pass", "Pass", "Ball Recovery", "Shot", "Shot"]
    assert e.iloc[0]["x"] == pytest.approx(60) and e.iloc[0]["y"] == pytest.approx(40) and e.iloc[0]["end_x"] == pytest.approx(84)
    assert pd.isna(e.iloc[0]["pass_outcome_name"]) and e.iloc[1]["pass_outcome_name"] == "Incomplete"
    shots = e[e["type_name"] == "Shot"]
    assert list(shots["shot_outcome_name"]) == ["Goal", "Saved"] and shots["shot_statsbomb_xg"].tolist() == [0.41, 0.08]
    assert list(e["period"]) == [1, 1, 1, 1, 2] and e["possession"].tolist() == [1, 1, 2, 3, 4]
    assert db.has_events(mid)                                                  # em cache para a próxima abertura
    assert "[events]" in inspect(str(d))


# --------------------------------------------------------------- consolidação
def test_consolidation_precedence_and_divergences(db):
    from src.data_hub.consolidate import compare

    def m(mid, src, lvl, h, a):
        return {"match_id": mid, "home_team_name": h, "away_team_name": a, "match_date": "2024-06-15", "home_score": 2,
                "away_score": 1, "competition_name": "x", "season_name": "2024", "status": "FT", "data_source": src,
                "data_level": lvl}
    db.upsert_matches([m(7_000_008_500, "brasileirao", DataLevel.BOXSCORE, "Flamengo", "Palmeiras"),
                       m(500_000_123, "espn", DataLevel.BOXSCORE, "Flamengo", "Palmeiras"),
                       m(2_000_000_555, "fdcouk", DataLevel.BOXSCORE, "Palmeiras", "Flamengo")])     # mandos trocados
    s = lambda t, k, v: {"team_name": t, "stat_key": k, "stat_label": k, "value": v}
    db.save_boxscore(7_000_008_500, {"team_stats": [s("Flamengo", "corners", 7), s("Flamengo", "shots_total", 15)],
                                     "lineups": [], "timeline": []})
    db.save_boxscore(500_000_123, {"team_stats": [s("Flamengo", "corners", 7), s("Flamengo", "shots_total", 16),
                                                  s("Flamengo", "possession_pct", 58)], "lineups": [], "timeline": []})
    db.save_boxscore(2_000_000_555, {"team_stats": [s("Flamengo", "corners", 6)], "lineups": [], "timeline": []})
    t = compare(db, 7_000_008_500).set_index(["stat_key", "side"])
    assert t.loc[("corners", "home"), "fonte escolhida"] == "brasileirao" and t.loc[("corners", "home"), "valor"] == 7
    assert t.loc[("corners", "home"), "diverge"]                               # fdcouk (com mando trocado) diz 6
    assert "fdcouk 6" in t.loc[("corners", "home"), "outras fontes"]
    assert t.loc[("shots_total", "home"), "diverge"] and t.loc[("shots_total", "home"), "valor"] == 15
    assert t.loc[("possession_pct", "home"), "fonte escolhida"] == "espn"     # só a ESPN tem posse
    assert compare(db, 9_999_999).empty


# ------------------------------------------------------- download automático
def test_openplay_downloads_latest_data_release_and_resumes(db, tmp_path, monkeypatch):
    from src.data_hub import net
    from src.data_hub.sources.openplay import OpenPlayProvider

    csv_m = b"match_id,date,home_team,away_team,home_score,away_score,competition,season\n5,2024-01-02,A,B,1,0,Liga,2023/2024\n"
    rel = [{"tag_name": "pipeline-v2", "assets": [{"name": "code.zip", "browser_download_url": "u0", "size": 9}]},
           {"tag_name": "data-v0.2.0", "assets": [{"name": "matches.csv", "browser_download_url": "u1", "size": len(csv_m)},
                                                  {"name": "README.md", "browser_download_url": "u2", "size": 3}]}]
    monkeypatch.setattr(net, "get", lambda url, **k: net.Response(200, __import__("json").dumps(rel).encode()))
    fetched = []

    def fake_download(url, dest, expected_size=None, **k):
        fetched.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(csv_m)
        return dest
    monkeypatch.setattr(net, "download", fake_download)
    p = OpenPlayProvider(db, path=str(tmp_path / "op"))
    out = p.sync()                                               # sem arquivos: baixa sozinho e cataloga
    assert fetched == ["u1"] and out["partidas"] == 1            # só a release de DADOS, só os arquivos de dados
    assert db.catalog("data_source = 'openplay'").iloc[0]["data_level"] == DataLevel.RESULT


def test_matches_built_from_team_rows_when_no_matches_table():
    from src.data_hub.sources.openplay import OpenPlayProvider

    ts = pd.DataFrame([{"match_id": 7, "date": "2024-05-01", "team": "Inter", "side": "home", "goals_for": 2,
                        "competition": "Serie A", "season": "2023/2024", "corners_taken": 5},
                       {"match_id": 7, "date": "2024-05-01", "team": "Milan", "side": "away", "goals_for": 1,
                        "competition": "Serie A", "season": "2023/2024", "corners_taken": 3}])
    m = OpenPlayProvider.matches_from_team_stats(ts)
    assert m.iloc[0][["home_team", "away_team", "home_score", "away_score"]].tolist() == ["Inter", "Milan", 2, 1]


def test_net_download_resumes_partial_file(tmp_path, monkeypatch):
    from src.data_hub import net

    body = b"0123456789" * 10
    calls = []

    class R:
        def __init__(self, headers):
            calls.append(headers.get("Range"))
            start = int(headers["Range"].split("=")[1].rstrip("-")) if headers.get("Range") else 0
            self.status_code = 206 if start else 200
            self._b = body[start:]
            self.headers = {"content-length": str(len(self._b))}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_content(self, n):
            yield self._b

    import types

    monkeypatch.setattr(net, "_httpx", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "requests",
                        types.SimpleNamespace(get=lambda url, headers=None, **k: R(headers or {}),
                                              RequestException=Exception))
    dest = tmp_path / "f.bin"
    (tmp_path / "f.bin.part").write_bytes(body[:40])            # download anterior caiu nos 40 bytes
    net.download("http://x/f.bin", dest, expected_size=len(body))
    assert dest.read_bytes() == body and calls == ["bytes=40-"]
    net.download("http://x/f.bin", dest, expected_size=len(body))  # já completo: não baixa de novo
    assert len(calls) == 1


def test_sync_everything_list_covers_all_sources_of_the_old_ingestion_code():
    from src.data_hub import sync

    old_code = {"openplay", "statsbomb", "api_football", "football_data", "open_matchday", "brasileirao", "cbf", "understat"}
    assert old_code <= set(sync.EVERYTHING) and sync.EVERYTHING[-1] == "lake"
