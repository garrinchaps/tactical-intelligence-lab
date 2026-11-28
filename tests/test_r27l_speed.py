"""Rodada 27l — velocidade sem mudar resultado: filtro por clube memorizado, conexões compartilhadas, consulta lenta."""
import threading

import pandas as pd

from src.data_lake import ids


def test_memoized_normalization_matches_original():
    for n in ["Grêmio Foot-Ball Porto Alegrense", "Atlético-MG", "São Paulo FC", "", "Kylian Mbappé", "N'Golo Kanté"]:
        assert ids.team_core(n) == ids._team_core_uncached(n)
        assert ids.player_core(n) == ids._player_core_uncached(n)
    assert ids.team_core(None) == ids._team_core_uncached(None)


def test_club_scoped_fast_path_equals_slow_path(monkeypatch):
    from src.scout import snapshot as S

    u = pd.DataFrame({"nome": ["A", "B", "C", "D"], "_core": ["a", "b", "c", "d"],
                      "clube": ["Cruzeiro", "Cruzeiro Esporte Clube", "", "Flamengo"],
                      "clube_tm": ["", "", "Cruzeiro", "Flamengo"], "pid": ["1", "2", "3", "4"]})
    monkeypatch.setattr(S, "cached_universe", lambda: u)
    S._MEMO.pop("idx_for", None)
    S._MEMO.pop("club_rows", None)
    slow = S._club_scoped_rows(u.copy(), "Cruzeiro")            # cópia → caminho antigo
    S._index()
    fast = S._club_scoped_rows(u, "Cruzeiro")                   # mercado inteiro → caminho rápido
    sub = S._club_scoped_rows(u.loc[[0, 1, 3]], "Cruzeiro")     # recorte do mercado → caminho rápido
    assert list(slow.index) == list(fast.index) == [0, 1, 2]
    assert list(sub.index) == [0, 1]


def test_pool_nested_and_threads(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("TACTICAL_DB_PATH", str(p))
    from src.data_hub.db import DataHubDB

    db = DataHubDB(p)
    with db.connect() as c:
        c.execute("CREATE TABLE z(a)")
    with db.connect() as a:
        with db.connect() as b:
            assert a is b
    def work():
        for _ in range(20):
            with db.connect() as c:
                c.execute("INSERT INTO z VALUES (1)")
    ts = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    with db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM z").fetchone()[0] == 80


def test_slow_query_is_logged(tmp_path, monkeypatch):
    from src.data_hub import db as D
    from src.ui import perf

    monkeypatch.setattr(perf, "PATH", tmp_path / "perf.jsonl")
    monkeypatch.setattr(D, "SLOW_SQL_S", 0.0)
    monkeypatch.delenv("TIL_IN_WORKER", raising=False)
    p = tmp_path / "t.db"
    monkeypatch.setenv("TACTICAL_DB_PATH", str(p))
    db = D.DataHubDB(p)
    with db.connect() as c:
        c.execute("SELECT 1").fetchall()
    assert any(r.get("tipo") == "sql" for r in perf.read(50))
