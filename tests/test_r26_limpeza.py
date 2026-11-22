import sqlite3

from src.tools import limpeza


def test_limpeza_nao_apaga_dados_e_mantem_fotografia_atual(tmp_path, monkeypatch):
    root = tmp_path
    (root / "data" / "processed").mkdir(parents=True)
    (root / "pkg" / "__pycache__").mkdir(parents=True)
    (root / "pkg" / "__pycache__" / "x.pyc").write_bytes(b"0" * 10)
    old = root / "data" / "processed" / "scout_universe_v2.pkl"
    old.write_bytes(b"1")
    monkeypatch.setattr(limpeza, "ROOT", root)
    from src.scout import snapshot
    cur = root / snapshot.SNAP_PATH
    cur.parent.mkdir(parents=True, exist_ok=True)
    cur.write_bytes(b"2")
    db = root / "t.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE matches (id INTEGER)")
    c.execute("INSERT INTO matches VALUES (1)")
    c.commit(); c.close()
    monkeypatch.setenv("TACTICAL_DB_PATH", str(db))
    log = []
    limpeza.project(False, log)
    limpeza.database(False, False, log)
    assert not old.exists() and cur.exists()
    assert not (root / "pkg" / "__pycache__").exists()
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 1
