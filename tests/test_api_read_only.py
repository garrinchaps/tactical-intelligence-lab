from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from apps.api.main import create_app


def _database(path):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "create table matches (match_id integer primary key, competition_name text, "
            "season_name text, match_date text, home_team_name text, away_team_name text, "
            "home_score integer, away_score integer, data_level text, data_source text)"
        )
        conn.executemany(
            "insert into matches values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "League", "2026", "2026-01-02", "A", "B", 1, 0, "RESULT", "fixture"),
                (2, "League", "2026", "2026-01-03", "C", "D", 2, 2, "EVENTS", "openplay"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_api_exposes_paged_shared_data_without_writing(tmp_path):
    db = tmp_path / "api.sqlite"
    _database(db)
    client = TestClient(create_app(db))

    response = client.get("/api/v1/matches", params={"data_level": "EVENTS"})
    assert response.status_code == 200
    assert response.json()["items"][0]["match_id"] == 2
    assert client.get("/api/v1/sources").json()["items"][0]["source"] == "fixture"

    with sqlite3.connect(db) as conn:
        assert conn.execute("select count(*) from matches").fetchone()[0] == 2


def test_api_readiness_requires_valid_database(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.sqlite"))
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 503


def test_protected_endpoint_requires_bearer_token(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.sqlite"))
    assert client.get("/api/v1/me").status_code == 401


def test_models_endpoint_exposes_cards_and_limitations(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.sqlite"))
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    assert response.json()["items"][0]["limitations"]


def test_fuzzy_endpoints_return_explanations(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.sqlite"))
    player = client.post("/api/v1/ai/fuzzy/player", json={"defensive_intensity": 80, "pass_accuracy": 90})
    pressure = client.post(
        "/api/v1/ai/fuzzy/pressure",
        json={"possession_pct": 65, "territorial_entries": 70, "shots": 50, "minute": 45},
    )
    assert player.status_code == 200 and player.json()["is_probability"] is False
    assert pressure.status_code == 200 and pressure.json()["rule_weights"]
