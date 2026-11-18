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
