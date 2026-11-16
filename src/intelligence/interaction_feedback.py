"""Registro de auditoria das interações do Analista IA.

Cada pergunta respondida gera um registro de telemetria SEM armazenar o texto da pergunta
ou a resposta. O feedback explícito do usuário é armazenado para revisão humana.
Feedback não altera pesos automaticamente: ele sinaliza exemplos para curadoria e avaliação.
"""
from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "feedback" / "assistant_interactions.sqlite3"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            interaction_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            match_id TEXT,
            engine TEXT,
            danger_model_version TEXT,
            query_sha256 TEXT NOT NULL,
            feedback INTEGER CHECK (feedback IN (-1, 1)),
            feedback_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_interactions_created ON interactions(created_at)")
    conn.commit()
    return conn


def record_interaction(question: str, match_id: Optional[int], engine: str = "",
                       danger_model_version: str = "") -> str:
    """Registra que houve uma pergunta; não guarda o conteúdo textual."""
    interaction_id = uuid.uuid4().hex
    digest = hashlib.sha256(str(question).encode("utf-8")).hexdigest()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO interactions
               (interaction_id, created_at, match_id, engine, danger_model_version, query_sha256)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (interaction_id, datetime.now(timezone.utc).isoformat(),
             str(match_id) if match_id is not None else None, engine or "",
             danger_model_version or "", digest),
        )
    return interaction_id


def set_feedback(interaction_id: str, helpful: bool) -> bool:
    """Anexa avaliação explícita à interação, sem treinar nenhum modelo."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE interactions SET feedback = ?, feedback_at = ? WHERE interaction_id = ?",
            (1 if helpful else -1, datetime.now(timezone.utc).isoformat(), interaction_id),
        )
        return cur.rowcount == 1


def feedback_summary() -> dict:
    with _connect() as conn:
        total, rated, positive, negative = conn.execute(
            """SELECT COUNT(*), SUM(feedback IS NOT NULL),
                      SUM(feedback = 1), SUM(feedback = -1)
               FROM interactions"""
        ).fetchone()
    return {"perguntas": int(total or 0), "avaliadas": int(rated or 0),
            "positivas": int(positive or 0), "negativas": int(negative or 0),
            "treinos_automaticos_por_interacao": 0}
