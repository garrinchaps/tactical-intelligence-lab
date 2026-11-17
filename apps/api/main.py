"""API read-only inicial, desacoplada da interface Streamlit."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware

from apps.api.auth import current_user
from src.machine_learning.model_catalog import model_cards
from src.intelligence.fuzzy import mamdani_player_rating, sugeno_pressure
from pydantic import BaseModel, Field


class FuzzyPlayerRequest(BaseModel):
    defensive_intensity: float = Field(ge=0, le=100)
    pass_accuracy: float = Field(ge=0, le=100)


class SugenoPressureRequest(BaseModel):
    possession_pct: float = Field(ge=0, le=100)
    territorial_entries: float = Field(ge=0, le=100)
    shots: float = Field(ge=0, le=100)
    minute: float = Field(default=0, ge=0, le=120)


DEFAULT_DB = Path("database/tactical_lab.db")


def _db_path(explicit: Path | str | None = None) -> Path:
    return Path(explicit or os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or DEFAULT_DB)


def _connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def _rows(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(query, params)
    columns = [description[0] for description in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def create_app(db_path: Path | str | None = None) -> FastAPI:
    path = _db_path(db_path)
    app = FastAPI(
        title="Tactical Intelligence Lab API",
        version="0.1.0",
        description="Contratos read-only para dados compartilhados do Data Hub.",
    )
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "TIL_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    bearer = HTTPBearer(auto_error=False)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        try:
            conn = _connect_read_only(path)
            try:
                result = conn.execute("PRAGMA quick_check").fetchone()
            finally:
                conn.close()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        if not result or result[0] != "ok":
            raise HTTPException(status_code=503, detail="database_not_ready")
        return {"status": "ready"}

    @app.get("/api/v1/matches")
    def matches(
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1_000_000),
        data_level: str | None = Query(None, pattern=r"^[A-Z_]{3,20}$"),
        data_source: str | None = Query(None, min_length=1, max_length=40),
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if data_level:
            clauses.append("data_level = ?")
            params.append(data_level)
        if data_source:
            clauses.append("data_source = ?")
            params.append(data_source)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = _connect_read_only(path)
        try:
            items = _rows(
                conn,
                "SELECT match_id, competition_name, season_name, match_date, "
                "home_team_name, away_team_name, home_score, away_score, data_level, data_source "
                f"FROM matches{where} ORDER BY match_date DESC, match_id DESC LIMIT ? OFFSET ?",
                tuple(params + [limit, offset]),
            )
        finally:
            conn.close()
        return {"items": items, "limit": limit, "offset": offset}

    @app.get("/api/v1/sources")
    def sources() -> dict[str, list[dict[str, Any]]]:
        conn = _connect_read_only(path)
        try:
            items = _rows(
                conn,
                "SELECT COALESCE(data_source, 'unknown') AS source, "
                "COUNT(*) AS matches, MAX(match_date) AS latest_match "
                "FROM matches GROUP BY COALESCE(data_source, 'unknown') ORDER BY source",
            )
        finally:
            conn.close()
        return {"items": items}

    @app.get("/api/v1/me")
    def me(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
        """Retorna somente claims mínimos do usuário autenticado."""
        return current_user(credentials)

    @app.get("/api/v1/models")
    def models() -> dict[str, list[dict[str, Any]]]:
        """Catálogo de modelos e limitações; não expõe pesos ou dados privados."""
        return {"items": model_cards()}

    @app.post("/api/v1/ai/fuzzy/player")
    def fuzzy_player(payload: FuzzyPlayerRequest) -> dict[str, Any]:
        return mamdani_player_rating(payload.defensive_intensity, payload.pass_accuracy)

    @app.post("/api/v1/ai/fuzzy/pressure")
    def fuzzy_pressure(payload: SugenoPressureRequest) -> dict[str, Any]:
        return sugeno_pressure(
            payload.possession_pct, payload.territorial_entries, payload.shots, minute=payload.minute
        )

    return app


app = create_app()
