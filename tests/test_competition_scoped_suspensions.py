from __future__ import annotations

import sqlite3

from src.squad.matchday import suspensions, yellow_suspensions


class SQLiteDB:
    def __init__(self, path):
        self.path = str(path)

    def connect(self):
        return sqlite3.connect(self.path)


def _db(tmp_path):
    path = tmp_path / "suspensions.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE matches (match_id INTEGER PRIMARY KEY, competition_name TEXT, match_date TEXT);
        CREATE TABLE match_timeline (
            match_id INTEGER, team_name TEXT, player_name TEXT, event_type TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return SQLiteDB(path)


def test_yellow_accumulation_does_not_cross_competitions(tmp_path):
    db = _db(tmp_path)
    with db.connect() as conn:
        conn.executemany(
            "INSERT INTO matches VALUES (?, ?, ?)",
            [
                (1, "Copa do Brasil", "2026-01-01"),
                (2, "Copa do Brasil", "2026-01-08"),
                (3, "Copa do Brasil", "2026-01-15"),
                (4, "Brasileirão Série A", "2026-01-20"),
            ],
        )
        conn.executemany(
            "INSERT INTO match_timeline VALUES (?, ?, ?, ?)",
            [(mid, "Santos", "Atleta", "Yellow Card") for mid in (1, 2, 3)],
        )
    assert yellow_suspensions(db, [1, 2, 3, 4], ["Santos"], "Brasileirão Série A") == {}
    result = yellow_suspensions(db, [1, 2, 3, 4], ["Santos"], "Copa do Brasil")
    assert "Atleta" in result
    assert "Copa do Brasil" in result["Atleta"]


def test_red_card_from_other_competition_is_not_carried_automatically(tmp_path):
    db = _db(tmp_path)
    with db.connect() as conn:
        conn.execute("INSERT INTO matches VALUES (1, 'Copa do Brasil', '2026-01-01')")
        conn.execute("INSERT INTO match_timeline VALUES (1, 'Santos', 'Atleta', 'Red Card')")
    assert suspensions(db, 1, ["Santos"], "Brasileirão Série A") == {}
    assert "Atleta" in suspensions(db, 1, ["Santos"], "Copa do Brasil")


def test_santos_and_santos_laguna_have_distinct_team_cores():
    from src.data_lake.ids import team_core

    assert team_core("Santos FC") == "santos"
    assert team_core("Santos Laguna") == "santos laguna"
    assert team_core("Santos FC") != team_core("Santos Laguna")
