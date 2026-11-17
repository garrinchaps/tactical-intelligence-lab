from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.project_audit import build_report, inspect_database, inspect_python


def test_inventory_discovers_pages_tests_connectors_and_symbols(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "import streamlit as st\n\ndef main():\n    return 1\n",
        encoding="utf-8",
    )
    page = tmp_path / "src" / "ui" / "pages" / "players.py"
    page.parent.mkdir(parents=True)
    page.write_text(
        "from src.data_hub.service import MatchDataService\n\n"
        "class PlayerPage:\n    pass\n",
        encoding="utf-8",
    )
    connector = tmp_path / "src" / "data_hub" / "sources" / "demo.py"
    connector.parent.mkdir(parents=True)
    connector.write_text("def fetch():\n    return None\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_demo.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_demo():\n    assert True\n", encoding="utf-8")

    inventory = inspect_python(tmp_path)

    assert inventory["python_file_count"] == 4
    assert "app.py" in inventory["page_entrypoints"]
    assert "src/ui/pages/players.py" in inventory["page_entrypoints"]
    assert "tests/test_demo.py" in inventory["test_files"]
    assert "src/data_hub/sources/demo.py" in inventory["connector_files"]
    assert inventory["symbols"]["app.py"]["functions"] == ["main"]
    assert inventory["symbols"]["src/ui/pages/players.py"]["classes"] == ["PlayerPage"]
    assert "src.data_hub.service" in inventory["internal_imports"]["src/ui/pages/players.py"]


def test_database_inventory_is_read_only_and_can_report_schema(tmp_path: Path):
    database = tmp_path / "sample.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY, home TEXT)")
        connection.execute("CREATE INDEX idx_matches_home ON matches(home)")
        connection.execute("INSERT INTO matches(home) VALUES ('A')")
        connection.commit()

    before = database.read_bytes()
    report = inspect_database(database, count_rows=True, check_integrity=True)

    assert report["exists"] is True
    assert report["read_only"] is True
    assert report["integrity_check"] == "ok"
    assert report["table_count"] == 1
    assert report["tables"][0]["name"] == "matches"
    assert report["tables"][0]["row_count"] == 1
    assert report["tables"][0]["indexes"]
    assert database.read_bytes() == before


def test_audit_records_syntax_errors_without_aborting(tmp_path: Path):
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n    pass\n", encoding="utf-8")

    report = build_report(tmp_path)

    assert report["python"]["python_file_count"] == 1
    assert report["python"]["syntax_errors"]
    assert report["database"] is None
