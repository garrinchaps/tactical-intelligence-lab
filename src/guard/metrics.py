"""Módulo 7.5 — Metrics: taxa de números não rastreáveis por resposta, antes e depois do guard."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd

from src.canonical.schema import utc_now_iso


@dataclass
class GuardRunMetrics:
    engine: str
    attempts: int
    outcome: str                     # APROVADO_1A | APROVADO_REGENERADO | DEGRADADO | LOCAL
    numbers_before: int
    untraceable_before: int
    numbers_after: int
    untraceable_after: int
    derived_after: int
    names_flagged_before: int

    @property
    def rate_before(self) -> float:
        return round(self.untraceable_before / self.numbers_before, 4) if self.numbers_before else 0.0

    @property
    def rate_after(self) -> float:
        return round(self.untraceable_after / self.numbers_after, 4) if self.numbers_after else 0.0

    def as_dict(self) -> dict:
        d = asdict(self)
        d.update(rate_before=self.rate_before, rate_after=self.rate_after)
        return d


class GuardMetricsLog:
    def __init__(self, db_path: Optional[Path | str] = "database/tactical_lab.db"):
        self.db_path = Path(db_path) if db_path else None

    def log(self, m: GuardRunMetrics) -> None:
        if not self.db_path or not self.db_path.parent.exists():
            return
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS guard_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT, logged_at TEXT, engine TEXT, attempts INTEGER, outcome TEXT,
                numbers_before INTEGER, untraceable_before INTEGER, rate_before REAL,
                numbers_after INTEGER, untraceable_after INTEGER, rate_after REAL, derived_after INTEGER,
                names_flagged_before INTEGER)""")
            conn.execute("""INSERT INTO guard_metrics (logged_at, engine, attempts, outcome, numbers_before,
                untraceable_before, rate_before, numbers_after, untraceable_after, rate_after, derived_after,
                names_flagged_before) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (utc_now_iso(), m.engine, m.attempts, m.outcome, m.numbers_before, m.untraceable_before,
                          m.rate_before, m.numbers_after, m.untraceable_after, m.rate_after, m.derived_after,
                          m.names_flagged_before))

    def history(self, limit: int = 200) -> pd.DataFrame:
        if not self.db_path or not self.db_path.exists():
            return pd.DataFrame()
        with sqlite3.connect(str(self.db_path)) as conn:
            try:
                return pd.read_sql_query(f"SELECT * FROM guard_metrics ORDER BY id DESC LIMIT {int(limit)}", conn)
            except Exception:
                return pd.DataFrame()
