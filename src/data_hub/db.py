"""
Acesso ao SQLite do Data Hub: migração do schema, catálogo unificado de partidas,
boxscore (estatísticas, escalações, linha do tempo, atletas), log de sincronização
e controle de cota das APIs.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

import pandas as pd

from src.data_hub.registry import (
    DataLevel,
    SIMULATED_ID_RANGES,
    UPLOAD_ID,
    source_from_internal_id,
    to_source_id,
)

DEFAULT_DB = Path("database/tactical_lab.db")
DEFAULT_SCHEMA = Path("database/schema.sql")

MATCH_EXTRA_COLUMNS = {
    "data_source": "TEXT",
    "data_level": "TEXT",
    "source_match_id": "TEXT",
    "country_name": "TEXT",
    "round_name": "TEXT",
    "status": "TEXT",
    "last_synced": "TEXT",
    "extra_json": "TEXT",
}

DATA_HUB_DDL = """
CREATE TABLE IF NOT EXISTS match_team_stats (
    match_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    stat_key TEXT NOT NULL,
    stat_label TEXT,
    value REAL,
    display_value TEXT,
    PRIMARY KEY (match_id, team_name, stat_key)
);
CREATE TABLE IF NOT EXISTS match_lineups (
    match_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    player_name TEXT NOT NULL,
    shirt_number TEXT,
    position TEXT,
    is_starter INTEGER DEFAULT 1,
    formation TEXT,
    coach TEXT,
    PRIMARY KEY (match_id, team_name, player_name)
);
CREATE TABLE IF NOT EXISTS match_timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    minute INTEGER,
    extra_minute INTEGER,
    team_name TEXT,
    player_name TEXT,
    related_player TEXT,
    event_type TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_timeline_match ON match_timeline(match_id);
CREATE TABLE IF NOT EXISTS match_player_stats (
    match_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    player_name TEXT NOT NULL,
    position TEXT,
    minutes INTEGER,
    rating REAL,
    stats_json TEXT,
    PRIMARY KEY (match_id, team_name, player_name)
);
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    matches_added INTEGER DEFAULT 0,
    matches_updated INTEGER DEFAULT 0,
    message TEXT
);
CREATE TABLE IF NOT EXISTS api_usage (
    provider TEXT NOT NULL,
    usage_date TEXT NOT NULL,
    requests INTEGER DEFAULT 0,
    PRIMARY KEY (provider, usage_date)
);
CREATE TABLE IF NOT EXISTS source_state (
    source TEXT NOT NULL,
    state_key TEXT NOT NULL,
    state_value TEXT,
    updated_at TEXT,
    PRIMARY KEY (source, state_key)
);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team_name, away_team_name);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _is_simulated(match_id: int) -> bool:
    return any(lo <= int(match_id) <= hi for lo, hi in SIMULATED_ID_RANGES)


class DataHubDB:
    """Wrapper fino sobre o SQLite com migração idempotente."""

    def __init__(self, db_path: Path | str = DEFAULT_DB, schema_path: Path | str = DEFAULT_SCHEMA):
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    # ------------------------------------------------------------------ infra
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def migrate(self) -> None:
        with self.connect() as conn:
            if self.schema_path.exists():
                conn.executescript(self.schema_path.read_text(encoding="utf-8"))
            cols = {r[1] for r in conn.execute("PRAGMA table_info(matches)").fetchall()}
            for col, typ in MATCH_EXTRA_COLUMNS.items():
                if col not in cols:
                    conn.execute(f"ALTER TABLE matches ADD COLUMN {col} {typ}")
            conn.executescript(DATA_HUB_DDL)
            # Classifica linhas antigas que ainda não têm fonte/nível
            rows = conn.execute(
                "SELECT match_id FROM matches WHERE data_source IS NULL OR data_level IS NULL"
            ).fetchall()
            for (mid,) in rows:
                src = source_from_internal_id(int(mid))
                if _is_simulated(int(mid)):
                    level = DataLevel.SIMULATED
                elif int(mid) == UPLOAD_ID:
                    level = DataLevel.UPLOAD
                else:
                    has_events = conn.execute(
                        "SELECT 1 FROM events WHERE match_id = ? LIMIT 1", (int(mid),)
                    ).fetchone()
                    level = DataLevel.EVENTS if (has_events or src in ("statsbomb", "wyscout")) else DataLevel.RESULT
                conn.execute(
                    "UPDATE matches SET data_source = ?, data_level = ?, source_match_id = ? WHERE match_id = ?",
                    (src, level, str(to_source_id(int(mid))), int(mid)),
                )

    # --------------------------------------------------------------- catálogo
    def upsert_matches(self, records: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        """Insere/atualiza partidas sem nunca rebaixar o nível de dado já existente."""
        rank = {DataLevel.RESULT: 1, DataLevel.BOXSCORE: 2, DataLevel.EVENTS: 3,
                DataLevel.SIMULATED: 0, DataLevel.UPLOAD: 0}
        added = updated = 0
        now = utc_now()
        with self.connect() as conn:
            for r in records:
                mid = int(r["match_id"])
                existing = conn.execute(
                    "SELECT data_level FROM matches WHERE match_id = ?", (mid,)
                ).fetchone()
                level = r.get("data_level") or DataLevel.RESULT
                if existing and existing[0] and rank.get(existing[0], 0) > rank.get(level, 0):
                    level = existing[0]
                values = (
                    mid,
                    int(r.get("competition_id") or 0),
                    str(r.get("competition_name") or "Desconhecida"),
                    int(r.get("season_id") or 0),
                    str(r.get("season_name") or ""),
                    str(r.get("match_date") or ""),
                    int(r.get("home_team_id") or 0),
                    str(r.get("home_team_name") or "Mandante"),
                    int(r.get("away_team_id") or 0),
                    str(r.get("away_team_name") or "Visitante"),
                    None if r.get("home_score") is None else int(r["home_score"]),
                    None if r.get("away_score") is None else int(r["away_score"]),
                    str(r.get("stadium_name") or ""),
                    str(r.get("referee_name") or ""),
                    int(r.get("has_360_data") or 0),
                    str(r.get("data_source") or source_from_internal_id(mid)),
                    level,
                    str(r.get("source_match_id") or to_source_id(mid)),
                    str(r.get("country_name") or ""),
                    str(r.get("round_name") or ""),
                    str(r.get("status") or "FT"),
                    now,
                    json.dumps(r.get("extra") or {}, ensure_ascii=False),
                )
                if existing:
                    conn.execute(
                        """UPDATE matches SET competition_id=?, competition_name=?, season_id=?, season_name=?,
                           match_date=?, home_team_id=?, home_team_name=?, away_team_id=?, away_team_name=?,
                           home_score=?, away_score=?, stadium_name=?, referee_name=?, has_360_data=?,
                           data_source=?, data_level=?, source_match_id=?, country_name=?, round_name=?,
                           status=?, last_synced=?, extra_json=? WHERE match_id=?""",
                        values[1:] + (mid,),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """INSERT INTO matches (match_id, competition_id, competition_name, season_id, season_name,
                           match_date, home_team_id, home_team_name, away_team_id, away_team_name, home_score,
                           away_score, stadium_name, referee_name, has_360_data, data_source, data_level,
                           source_match_id, country_name, round_name, status, last_synced, extra_json)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        values,
                    )
                    added += 1
        return {"added": added, "updated": updated}

    def set_level(self, match_id: int, level: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE matches SET data_level = ?, last_synced = ? WHERE match_id = ?",
                (level, utc_now(), int(match_id)),
            )

    def get_match(self, match_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM matches WHERE match_id = ?", (int(match_id),)).fetchone()
        return dict(row) if row else None

    def catalog(self, where: str = "", params: tuple = (), limit: Optional[int] = None) -> pd.DataFrame:
        sql = "SELECT * FROM matches"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY match_date DESC, match_id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self.connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    def has_events(self, match_id: int) -> bool:
        with self.connect() as conn:
            return conn.execute(
                "SELECT 1 FROM events WHERE match_id = ? LIMIT 1", (int(match_id),)
            ).fetchone() is not None

    def has_boxscore(self, match_id: int) -> bool:
        with self.connect() as conn:
            return conn.execute(
                "SELECT 1 FROM match_team_stats WHERE match_id = ? LIMIT 1", (int(match_id),)
            ).fetchone() is not None or conn.execute(
                "SELECT 1 FROM match_lineups WHERE match_id = ? LIMIT 1", (int(match_id),)
            ).fetchone() is not None

    def save_events(self, match_id: int, df_events: pd.DataFrame) -> None:
        if df_events is None or df_events.empty:
            return
        with self.connect() as conn:
            event_cols = [r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()]
            df = df_events[[c for c in df_events.columns if c in event_cols]].copy()
            conn.execute("DELETE FROM events WHERE match_id = ?", (int(match_id),))
            df.to_sql("events", conn, if_exists="append", index=False)

    def load_events(self, match_id: int) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM events WHERE match_id = ? ORDER BY period, index_num", conn,
                params=(int(match_id),),
            )

    # --------------------------------------------------------------- boxscore
    def save_boxscore(self, match_id: int, box: Dict[str, Any]) -> None:
        mid = int(match_id)
        with self.connect() as conn:
            for table in ("match_team_stats", "match_lineups", "match_timeline", "match_player_stats"):
                conn.execute(f"DELETE FROM {table} WHERE match_id = ?", (mid,))
            for s in box.get("team_stats", []):
                conn.execute(
                    "INSERT OR REPLACE INTO match_team_stats VALUES (?,?,?,?,?,?)",
                    (mid, s["team_name"], s["stat_key"], s.get("stat_label"), s.get("value"),
                     s.get("display_value")),
                )
            for p in box.get("lineups", []):
                conn.execute(
                    "INSERT OR REPLACE INTO match_lineups VALUES (?,?,?,?,?,?,?,?)",
                    (mid, p["team_name"], p["player_name"], p.get("shirt_number"), p.get("position"),
                     int(p.get("is_starter", 1)), p.get("formation"), p.get("coach")),
                )
            for e in box.get("timeline", []):
                conn.execute(
                    """INSERT INTO match_timeline (match_id, minute, extra_minute, team_name, player_name,
                       related_player, event_type, detail) VALUES (?,?,?,?,?,?,?,?)""",
                    (mid, e.get("minute"), e.get("extra_minute"), e.get("team_name"), e.get("player_name"),
                     e.get("related_player"), e.get("event_type"), e.get("detail")),
                )
            for p in box.get("player_stats", []):
                conn.execute(
                    "INSERT OR REPLACE INTO match_player_stats VALUES (?,?,?,?,?,?,?)",
                    (mid, p["team_name"], p["player_name"], p.get("position"), p.get("minutes"),
                     p.get("rating"), json.dumps(p.get("stats") or {}, ensure_ascii=False)),
                )

    def load_boxscore(self, match_id: int) -> Dict[str, Any]:
        mid = int(match_id)
        with self.connect() as conn:
            stats = pd.read_sql_query("SELECT * FROM match_team_stats WHERE match_id = ?", conn, params=(mid,))
            lineups = pd.read_sql_query("SELECT * FROM match_lineups WHERE match_id = ?", conn, params=(mid,))
            timeline = pd.read_sql_query(
                "SELECT * FROM match_timeline WHERE match_id = ? ORDER BY minute, extra_minute, id", conn,
                params=(mid,),
            )
            players = pd.read_sql_query("SELECT * FROM match_player_stats WHERE match_id = ?", conn, params=(mid,))
        if not players.empty:
            players["stats"] = players["stats_json"].apply(lambda s: json.loads(s) if s else {})
        return {"team_stats": stats, "lineups": lineups, "timeline": timeline, "player_stats": players}

    # --------------------------------------------------------- cota e estado
    def api_usage_today(self, provider: str) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT requests FROM api_usage WHERE provider = ? AND usage_date = ?", (provider, today)
            ).fetchone()
        return int(row[0]) if row else 0

    def register_api_call(self, provider: str, n: int = 1) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO api_usage (provider, usage_date, requests) VALUES (?,?,?)
                   ON CONFLICT(provider, usage_date) DO UPDATE SET requests = requests + excluded.requests""",
                (provider, today, int(n)),
            )

    def get_state(self, source: str, key: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT state_value FROM source_state WHERE source = ? AND state_key = ?", (source, key)
            ).fetchone()
        return row[0] if row else None

    def set_state(self, source: str, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO source_state (source, state_key, state_value, updated_at) VALUES (?,?,?,?)
                   ON CONFLICT(source, state_key) DO UPDATE SET state_value = excluded.state_value,
                   updated_at = excluded.updated_at""",
                (source, key, value, utc_now()),
            )

    def log_sync(self, source: str, started_at: str, status: str, added: int, updated: int, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO sync_runs (source, started_at, finished_at, status, matches_added,
                   matches_updated, message) VALUES (?,?,?,?,?,?,?)""",
                (source, started_at, utc_now(), status, int(added), int(updated), message[:2000]),
            )

    def sync_history(self, limit: int = 30) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                f"SELECT * FROM sync_runs ORDER BY id DESC LIMIT {int(limit)}", conn
            )

    def coverage(self) -> pd.DataFrame:
        """Resumo da base: partidas por fonte, nível e competição."""
        with self.connect() as conn:
            return pd.read_sql_query(
                """SELECT data_source, data_level, competition_name, season_name,
                          COUNT(*) AS partidas,
                          SUM(CASE WHEN match_id IN (SELECT DISTINCT match_id FROM events) THEN 1 ELSE 0 END)
                              AS com_eventos_baixados,
                          MAX(match_date) AS jogo_mais_recente
                   FROM matches GROUP BY data_source, data_level, competition_name, season_name
                   ORDER BY jogo_mais_recente DESC""",
                conn,
            )
