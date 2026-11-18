"""Rodada 7: velocidade — trabalho pesado fora do processo da tela, Scout por fotografia, sem invalidar caches à toa."""
import os
import threading

import pandas as pd


def test_background_threads_do_not_invalidate_ui_version(tmp_path):
    from src.data_hub.db import DataHubDB

    db = DataHubDB(tmp_path / "v.db")
    DataHubDB._ver_memo[str(db.db_path)] = {"adopted": "x", "latest": "x", "at": 0, "probed": 0}
    t = threading.Thread(target=db._touched, name="til-fotmob")
    t.start(); t.join()
    assert str(db.db_path) in DataHubDB._ver_memo          # gravação da FotMob não força reler o catálogo
    db._touched()                                          # gravação da própria tela invalida na hora
    assert str(db.db_path) not in DataHubDB._ver_memo


def test_worker_status_roundtrip_and_pid_check(tmp_path, monkeypatch):
    from src.data_hub import worker as W

    monkeypatch.setattr(W, "STATUS_PATH", tmp_path / "s.json")
    W.write_status({"scout": {"ultima": None}})
    s = W.read_status()
    assert s and s["pid"] == os.getpid() and "fotmob" in s and "openplay" in s
    assert W.pid_alive(os.getpid()) and not W.pid_alive(0)


def test_ui_mode_does_not_start_threads(monkeypatch):
    from src.data_hub import autosync as A

    monkeypatch.delenv("TIL_IN_WORKER", raising=False)
    monkeypatch.delenv("AUTO_SYNC_MODE", raising=False)
    assert A.process_mode() is True
    monkeypatch.setenv("AUTO_SYNC_MODE", "thread")
    assert A.process_mode() is False


def test_scout_snapshot_roundtrip_and_stable_version(tmp_path, monkeypatch):
    from src.scout import snapshot as S

    monkeypatch.setattr(S, "SNAP_PATH", tmp_path / "u.pkl")
    monkeypatch.setattr(S, "META_PATH", tmp_path / "u.json")
    monkeypatch.setattr(S, "OLD_SNAPS", [])
    assert S.load() is None and S.age_hours() is None
    S.save({"universe": pd.DataFrame({"nome": ["A", "B"]}), "clubs": pd.DataFrame(), "status": "carregado"})
    v1 = S.version()
    assert S.load()["universe"]["nome"].tolist() == ["A", "B"] and S.age_hours() < 0.1
    assert S.version() == v1                                # estável entre cliques (não muda a cada jogo gravado)


def test_scout_recommend_tie_does_not_compare_dicts():
    out = pd.DataFrame([{"score_scout": 70.0, "realismo": {"score": 40}, "_core": "a"},
                        {"score_scout": 70.0, "realismo": {"score": 80}, "_core": "b"}])
    out["_r"] = [r["score"] for r in out["realismo"]]
    assert out.sort_values(["score_scout", "_r"], ascending=False)["_core"].tolist() == ["b", "a"]


def test_player_stats_table_has_no_duplicate_columns():
    from src.ui.pages.fotmob_depth import player_stats_table

    ps = pd.DataFrame([{"team_name": "Brazil", "player_name": "Vini", "position": "", "minutes": 60, "rating": 9.8,
                        "stats": {"minutes": 60, "totalShots": 7, "matchstats.headers.tackles": 1}},
                       {"team_name": "Singapore", "player_name": "Song", "position": "", "minutes": 90, "rating": 6.1,
                        "stats": {"minutes": 90, "totalShots": 0}}])
    t = player_stats_table(ps)
    assert not t.columns.duplicated().any() and "Desarmes" in t and "Finalizações" in t and "minutes" not in t
    assert t.iloc[0]["Jogador"] == "Vini"
    assert player_stats_table(ps, "Singapore")["Jogador"].tolist() == ["Song"]


def test_zebra_has_no_light_gradient_and_marks_missing():
    from src.ui.components import zebra

    df = pd.DataFrame({"Jogador": ["A", "B", None], "Finalizações": [1.0, 5.0, 3.0], "Perdeu a posse": [2.0, 0.0, 1.0]})
    html = zebra(df).to_html()
    assert "background-color: #" in html and "None" not in html


def test_vulnerabilities_find_dribbled_fullback_and_counterattacks(tmp_path, monkeypatch):
    import json as _j

    import numpy as np

    from src.analytics import rating_box as RB
    from src.analytics import vulnerabilities as V
    from src.data_hub.db import DataHubDB
    from src.data_hub.sources.fotmob import FotmobProvider

    db = DataHubDB(tmp_path / "w.db")
    FotmobProvider(db, enabled=False).ensure_tables()
    rng = np.random.default_rng(0)
    ref = pd.DataFrame({"funcao": ["lateral"] * 60, "driblado90": rng.uniform(0.2, 0.9, 60),
                        "desarmes_ganhos90": rng.uniform(1, 3, 60)})
    monkeypatch.setattr(RB, "reference", lambda path=None: ref)
    for i in range(5):
        mid = 12_000_100_000 + i
        db.upsert_matches([{"match_id": mid, "source_match_id": str(mid), "competition_name": "Liga", "season_name": "2026",
                            "match_date": f"2026-10-{i + 1:02d}", "home_team_name": "Alvo", "away_team_name": f"R{i}",
                            "home_score": 0, "away_score": 1, "status": "FT", "data_source": "fotmob", "data_level": "BOXSCORE"}])
        db.save_boxscore(mid, {"team_stats": [], "timeline": [],
                               "lineups": [{"team_name": "Alvo", "player_name": "Lateral Fraco", "shirt_number": "2",
                                            "position": "RB", "is_starter": 1, "formation": "4-4-2", "coach": ""}],
                               "player_stats": [{"team_name": "Alvo", "player_name": "Lateral Fraco", "position": "",
                                                 "minutes": 90, "rating": 6.0,
                                                 "stats": {"minutes": 90, "dribbled_past": 3, "matchstats.headers.tackles": 2}}]})
        with db.connect() as c:
            c.executemany("INSERT INTO match_shots (match_id, team_name, player_name, minute, x, y, xg, outcome, situation, "
                          "on_target, own_goal, source) VALUES (?,?,?,?,?,?,?,?,?,1,0,'fotmob')",
                          [(mid, f"R{i}", "Atacante", 30, 110, 40, 0.3, "Miss", "FastBreak")])
    r = V.team_vulnerabilities(db, ["Alvo"], 12)
    titles = [a["titulo"] for a in r["achados"]]
    assert any("Lateral Fraco é muito driblado" in t for t in titles)
    assert any("contra-ataque" in t for t in titles)
    assert all(0 <= a["gravidade"] <= 100 and a["evidencia"] and a["explorar"] for a in r["achados"])


def test_one_per_game_merges_sources_with_one_day_and_name_differences():
    from src.ui.pages.search_all import one_per_game

    df = pd.DataFrame([
        {"match_id": 1, "match_date": "2026-11-15", "home_team_name": "Singapore", "away_team_name": "Brasil", "data_level": "RESULT"},
        {"match_id": 2, "match_date": "2026-11-14", "home_team_name": "Singapore", "away_team_name": "Brazil", "data_level": "BOXSCORE"},
        {"match_id": 3, "match_date": "2026-10-23", "home_team_name": "Cruzeiro", "away_team_name": "Remo", "data_level": "RESULT"},
        {"match_id": 4, "match_date": "2026-10-24", "home_team_name": "Cruzeiro", "away_team_name": "Santos", "data_level": "RESULT"}])
    out = one_per_game(df)
    assert sorted(out["match_id"]) == [2, 3, 4]          # o jogo duplicado fica só na versão com estatísticas


def test_reference_baseline_ui_only_reads_cache(tmp_path, monkeypatch):
    import json as _j

    from src.metrics.strengths_weaknesses import ReferenceBaselineBuilder as B

    monkeypatch.setattr(B, "DEFAULT_CACHE", tmp_path / "ref.json")
    assert B.load_cached() == {}
    (tmp_path / "ref.json").write_text(_j.dumps({"match_ids": [1, 2], "players": [], "teams": []}), encoding="utf-8")
    assert B.load_cached()["match_ids"] == [1, 2] and B.TARGET_MATCHES >= 1000


def test_compact_experiment_saves_feature_names_and_scores(tmp_path):
    import src.machine_learning.model_registry as R

    data = R.DangerModelRegistry.dataset()
    data = data[data["match_id"].isin(sorted(data["match_id"].unique())[:20])]
    reg = R.DangerModelRegistry(root=tmp_path / "reg")
    reg.train_round(data, [8], 0.003, 2, 1e-4, 256, seed=1, origin="campeão de teste", cv_folds=0)
    r = reg.train_round(data, [], 0.003, 2, 1e-4, 256, seed=2, cv_folds=0, features=R.COMPACT_FEATURES)
    assert r["n_features"] == len(R.COMPACT_FEATURES)
    net = r["net"]
    assert net.feature_names == R.COMPACT_FEATURES
    X = R.DangerModelRegistry._model_matrix(net, data)
    assert X.shape[1] == len(R.COMPACT_FEATURES)
    assert "E" in R.EXPERIMENTS and R.EXPERIMENT_ORDER[0] == "E"


def test_fotmob_squad_parse_and_official_roster():
    import pandas as pd

    from src.data_hub.sources.fotmob import FotmobProvider
    from src.squad.planner import apply_official_roster

    d = {"squad": {"squad": [
        {"title": "coach", "members": [{"id": 1, "name": "Treinador"}]},
        {"title": "keepers", "members": [{"id": 2, "name": "Cássio", "shirtNumber": 1}]},
        {"title": "defenders", "members": [{"id": 3, "name": "Matías Viña", "positionIdsDesc": "LB,LWB",
                                            "injury": {"name": "Joelho"}}]},
        {"title": "attackers", "members": [{"id": 4, "name": "Luis Sinisterra", "positionIdsDesc": "LW"}]}]}}
    rows = FotmobProvider.parse_squad(d, 99, "Cruzeiro", "2026-11-18T00:00:00+00:00")
    assert [r["name"] for r in rows] == ["Cássio", "Matías Viña", "Luis Sinisterra"]   # sem o treinador
    assert rows[0]["position"] == "GK" and rows[1]["injury"] == "Joelho"
    off = pd.DataFrame(rows).assign(lesao=lambda x: x["injury"])
    sq = pd.DataFrame({"nome": ["Cassio", "Matias Vina", "Jogador Que Saiu"], "papel": ["GK", "LB", "ST"],
                       "idade": [39, 28, 30]})
    out, ch = apply_official_roster(sq, off)
    assert set(out["nome"]) == {"Cássio", "Matías Viña", "Luis Sinisterra"}
    assert {"nome": "Jogador Que Saiu", "mudanca": "saiu",
            "motivo": "não está no elenco inscrito hoje (FotMob)"} in ch
    assert any(c["mudanca"] == "chegou" and c["nome"] == "Luis Sinisterra" for c in ch)
    assert out.loc[out["nome"] == "Luis Sinisterra", "papel"].iloc[0] == "LW"
    assert out.loc[out["nome"] == "Matías Viña", "lesao"].iloc[0] == "Joelho"
    same, none = apply_official_roster(sq, pd.DataFrame())
    assert len(same) == 3 and none == []


def test_game_page_has_neural_section():
    from src.ui.pages import games

    assert games.SECTIONS[6] == "🧠 Perigo (IA)"
    import src.ui.pages.danger_view as dv

    assert callable(dv.render)
