from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path

import pytest

from scripts import fetch_db


def _make_database(path: Path, *, table: str = "local_records", value: str = "keep-me") -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE {table} (value TEXT NOT NULL)")
        connection.execute(f"INSERT INTO {table}(value) VALUES (?)", (value,))
        connection.commit()


def _make_remote_gzip(tmp_path: Path) -> Path:
    source_db = tmp_path / "remote.db"
    _make_database(source_db, table="remote_records", value="remote-copy")
    compressed = tmp_path / "remote.db.gz"
    with open(source_db, "rb") as source, gzip.open(compressed, "wb") as destination:
        destination.write(source.read())
    return compressed


def test_existing_large_database_is_preserved_without_network(monkeypatch, tmp_path):
    database = tmp_path / "large.db"
    database.write_bytes(b"x" * (fetch_db.LARGE_DB_BYTES + 1))
    monkeypatch.setenv("TACTICAL_DB_PATH", str(database))
    monkeypatch.delenv("HF_TOKEN", raising=False)

    result = fetch_db.ensure_database()

    assert result == str(database)
    assert database.stat().st_size == fetch_db.LARGE_DB_BYTES + 1


def test_existing_small_database_with_tables_is_not_overwritten(monkeypatch, tmp_path):
    database = tmp_path / "local.db"
    _make_database(database)
    before = database.read_bytes()
    monkeypatch.setenv("TACTICAL_DB_PATH", str(database))
    monkeypatch.delenv(fetch_db.DB_REPLACE_ENV, raising=False)
    monkeypatch.setenv("HF_TOKEN", "not-used")

    with pytest.raises(RuntimeError, match="Nenhum dado foi substituído"):
        fetch_db.ensure_database()

    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM local_records").fetchone()[0] == "keep-me"


def test_explicit_replace_creates_consistent_backup(monkeypatch, tmp_path):
    database = tmp_path / "local.db"
    _make_database(database)
    original_value = "keep-me"
    remote_gzip = _make_remote_gzip(tmp_path)

    monkeypatch.setenv("TACTICAL_DB_PATH", str(database))
    monkeypatch.setenv(fetch_db.DB_REPLACE_ENV, "1")
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setattr(fetch_db, "hf_hub_download", lambda **kwargs: str(remote_gzip), raising=False)

    # hf_hub_download é importado dentro de ensure_database; injeta módulo substituto.
    import sys
    import types

    fake_module = types.ModuleType("huggingface_hub")
    fake_module.hf_hub_download = lambda **kwargs: str(remote_gzip)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_module)

    fetch_db.ensure_database()

    backups = list(tmp_path.glob("local.db.pre-fetch-*.bak"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute("SELECT value FROM local_records").fetchone()[0] == original_value
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM remote_records").fetchone()[0] == "remote-copy"


def test_datahub_uses_tactical_db_path_alias(monkeypatch, tmp_path):
    from src.data_hub.db import DataHubDB

    target = tmp_path / "tactical-path" / "db.sqlite"
    monkeypatch.setenv("TACTICAL_DB_PATH", str(target))
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.setattr(DataHubDB, "migrate", lambda self: None)

    db = DataHubDB()

    assert db.db_path == target
    assert target.parent.is_dir()
