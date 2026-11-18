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


class LabAskRequest(BaseModel):
    match_id: int
    question: str = Field(min_length=2, max_length=500)
    focus: str | None = None


class GeneticPlayer(BaseModel):
    nome: str
    papel: str
    nota: float = Field(default=50, ge=0, le=100)
    drible: float | None = Field(default=None, ge=0, le=1)
    cruzamento: float | None = Field(default=None, ge=0, le=1)
    aereo: float | None = Field(default=None, ge=0, le=1)
    finalizacao: float | None = Field(default=None, ge=0, le=1)
    pressao: float | None = Field(default=None, ge=0, le=1)
    altura_cm: float | None = None
    lesao: str | None = None


class GeneticRequest(BaseModel):
    players: list[GeneticPlayer] = Field(min_length=11, max_length=60)
    formation: str = "4-3-3"
    findings: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    seed: int = 42
    generations: int = Field(default=150, ge=10, le=500)


class _ReadOnlyDB:
    """O mínimo que a IA do laboratório precisa do banco, sempre em modo somente leitura."""

    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        return _connect_read_only(self.path)

    def load_events(self, match_id: int):
        import pandas as pd

        conn = self.connect()
        try:
            return pd.read_sql_query("SELECT * FROM events WHERE match_id = ? ORDER BY period, index_num", conn,
                                     params=(int(match_id),))
        finally:
            conn.close()

    def load_boxscore(self, match_id: int):
        import json as _json

        import pandas as pd

        conn = self.connect()
        try:
            stats = pd.read_sql_query("SELECT * FROM match_team_stats WHERE match_id = ?", conn, params=(int(match_id),))
            players = pd.read_sql_query("SELECT * FROM match_player_stats WHERE match_id = ?", conn, params=(int(match_id),))
        finally:
            conn.close()
        if not players.empty:
            players["stats"] = players["stats_json"].apply(lambda x: _json.loads(x) if x else {})
        return {"team_stats": stats, "player_stats": players}


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

    def _match_inputs(match_id: int):
        try:
            conn = _connect_read_only(path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail="Banco de dados indisponível.") from exc
        try:
            rows = _rows(conn, "SELECT match_id, home_team_name, away_team_name, data_level, data_source, "
                               "competition_name, match_date FROM matches WHERE match_id = ?", (int(match_id),))
        finally:
            conn.close()
        if not rows:
            raise HTTPException(status_code=404, detail="Partida não encontrada.")
        meta = rows[0]
        db = _ReadOnlyDB(path)
        df = db.load_events(match_id) if meta.get("data_level") == "EVENTS" else None
        box = db.load_boxscore(match_id)
        return meta, (df if df is not None and not df.empty else None), box, db

    @app.post("/api/v1/ai/lab/ask")
    def lab_ask(payload: LabAskRequest) -> dict[str, Any]:
        """IA do laboratório: responde a pergunta com os números do jogo (não registra nada pela API)."""
        from src.intelligence.lab_ai import engine as lab

        meta, df, box, db = _match_inputs(payload.match_id)
        r = lab.answer(payload.question, meta, df, box, payload.focus, db=db)
        return {"match": meta, "markdown": r["markdown"], "engine": r["engine"], "n_facts": r["n_facts"],
                "facts": [{k: f[k] for k in ("key", "team", "player", "score")} for f in r["facts"]]}

    @app.get("/api/v1/matches/{match_id}/report")
    def lab_report(match_id: int, focus: str | None = None) -> dict[str, Any]:
        """Relatório completo da IA do laboratório para a partida."""
        from src.intelligence.lab_ai import engine as lab

        meta, df, box, db = _match_inputs(match_id)
        return {"match": meta, **lab.report(meta, df, box, focus, db=db)}

    @app.post("/api/v1/ai/genetic/lineup")
    def genetic_lineup(payload: GeneticRequest) -> dict[str, Any]:
        """Algoritmo genético de escalação contra as fraquezas informadas (comparado com o melhor XI húngaro)."""
        import pandas as pd

        from src.squad.formations import FORMATIONS
        from src.squad.genetic import LineupGA

        if payload.formation not in FORMATIONS:
            raise HTTPException(status_code=422, detail=f"Formação desconhecida. Opções: {', '.join(FORMATIONS)}")
        sq = pd.DataFrame([p.model_dump() for p in payload.players])
        r = LineupGA(sq, payload.formation, payload.findings, seed=payload.seed, generations=payload.generations).run()
        r["historico"] = r["historico"][-50:]
        return r

    return app


app = create_app()
