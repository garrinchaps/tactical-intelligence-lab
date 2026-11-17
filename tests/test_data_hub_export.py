from __future__ import annotations

import json
import sqlite3

import pytest

from src.data_hub.export import export_table


def _database(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute("create table matches (match_id integer, season text, source text)")
        conn.executemany(
            "insert into matches values (?, ?, ?)",
            [(1, "2025", "fixture"), (2, "2026", "fixture")],
        )
        conn.commit()
    finally:
        conn.close()


def test_export_table_is_selective_read_only_and_manifested(tmp_path):
    db = tmp_path / "source.sqlite"
    _database(db)
    result = export_table(
        db,
        table="matches",
        columns=["match_id", "season"],
        where="season = ?",
        params=("2026",),
        destination=tmp_path / "out" / "matches.csv.gz",
        source="fixture",
        connector="test",
        license="CC BY 4.0",
        redistributable=True,
    )

    assert result.rows == 1
    assert result.artifact.exists()
    payload = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert payload["row_count"] == 1
    assert payload["columns"] == ["match_id", "season"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("select count(*) from matches").fetchone()[0] == 2


def test_export_rejects_untrusted_identifier(tmp_path):
    db = tmp_path / "source.sqlite"
    _database(db)
    with pytest.raises(ValueError):
        export_table(
            db,
            table="matches; drop table matches",
            destination=tmp_path / "out.csv.gz",
            source="x",
            connector="x",
            license="unknown",
        )
