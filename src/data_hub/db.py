"""
Acesso ao SQLite do Data Hub: migração do schema, catálogo unificado de partidas,
boxscore (estatísticas, escalações, linha do tempo, atletas), log de sincronização
e controle de cota das APIs.
"""

from __future__ import annotations

import json
import os
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
CREATE INDEX IF NOT EXISTS idx_matches_level_source ON matches(data_level, data_source);
CREATE INDEX IF NOT EXISTS idx_team_stats_match ON match_team_stats(match_id);
-- v36 (velocidade): jogador na busca/scout, escalações por time, números por jogador, fonte+data
CREATE INDEX IF NOT EXISTS idx_lineups_team ON match_lineups(team_name, match_id);
CREATE INDEX IF NOT EXISTS idx_lineups_player ON match_lineups(player_name);
CREATE INDEX IF NOT EXISTS idx_pstats_match ON match_player_stats(match_id, team_name);
CREATE INDEX IF NOT EXISTS idx_pstats_player ON match_player_stats(player_name, match_id);
CREATE INDEX IF NOT EXISTS idx_lineups_coach ON match_lineups(coach, match_id);
CREATE INDEX IF NOT EXISTS idx_matches_source_date ON matches(data_source, match_date);

-- Revisão leve do catálogo: triggers também capturam gravações feitas por outros processos.
CREATE TRIGGER IF NOT EXISTS trg_matches_catalog_insert AFTER INSERT ON matches BEGIN
    UPDATE source_state SET state_value = CAST(COALESCE(state_value, '0') AS INTEGER) + 1,
        updated_at = CURRENT_TIMESTAMP WHERE source='cache' AND state_key='catalog_revision';
END;
CREATE TRIGGER IF NOT EXISTS trg_matches_catalog_update AFTER UPDATE ON matches BEGIN
    UPDATE source_state SET state_value = CAST(COALESCE(state_value, '0') AS INTEGER) + 1,
        updated_at = CURRENT_TIMESTAMP WHERE source='cache' AND state_key='catalog_revision';
END;
CREATE TRIGGER IF NOT EXISTS trg_matches_catalog_delete AFTER DELETE ON matches BEGIN
    UPDATE source_state SET state_value = CAST(COALESCE(state_value, '0') AS INTEGER) + 1,
        updated_at = CURRENT_TIMESTAMP WHERE source='cache' AND state_key='catalog_revision';
END;
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _is_simulated(match_id: int) -> bool:
    return any(lo <= int(match_id) <= hi for lo, hi in SIMULATED_ID_RANGES)


MAIN_STATS = ("shots_total", "shots_on_target", "possession_pct", "passes_total", "corners", "fouls",
              "yellow_cards", "xg", "saves", "offsides")


# rodada 13 (velocidade): "jogos do time" filtra mandante OU visitante — sem índice pelo visitante, cada consulta varria
# a tabela inteira. Criar estes índices numa base de 300 mil jogos leva minutos, por isso NÃO roda ao abrir o banco
# (travava o app e os testes): roda no processo de fundo com a tela parada ou pelo comando
# `python -m src.tools.criar_indices` (com o app fechado).
SPEED_INDEXES = [
    ("idx_matches_home_date", "matches(home_team_name, match_date)"),
    ("idx_matches_away_date", "matches(away_team_name, match_date)"),
    ("idx_matches_comp_date", "matches(competition_name, match_date)"),
    ("idx_pstats_team", "match_player_stats(team_name, match_id)"),
    ("idx_lineups_match", "match_lineups(match_id)"),
    ("idx_team_stats_team", "match_team_stats(team_name, match_id)"),
]


_TLS = __import__("threading").local()


def _reuse_enabled(path: Path) -> bool:
    if os.getenv("TIL_REUSE_CONN", "1") == "0":
        return False
    main = Path(os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or str(DEFAULT_DB))
    try:
        return Path(path).resolve() == main.resolve()
    except OSError:
        return False


def _thread_conn(db: "DataHubDB") -> sqlite3.Connection:
    key = str(Path(db.db_path).resolve())
    pool = getattr(_TLS, "pool", None)
    if pool is None:
        pool = _TLS.pool = {}
    conn = pool.get(key)
    if conn is None:
        conn = pool[key] = db._open()
    return conn


FROZEN_SETTLE_S = 3 * 3600


def _frozen() -> bool:
    try:
        from src.data_hub.activity import frozen

        return frozen()
    except Exception:
        return False


_MIGRATED: set = set()
_MIG_LOCK = __import__("threading").Lock()


def _migration_key(path: Path):
    """(arquivo, identidade no disco): se o arquivo for apagado e recriado (testes), migra de novo."""
    try:
        p = Path(path).resolve()
        st_ = p.stat()
    except OSError:
        return None
    try:                                     # versão do esquema: base antiga reaberta → migra (backfills legados)
        c = sqlite3.connect(str(p), timeout=1)
        try:
            uv = int((c.execute("PRAGMA user_version").fetchone() or [0])[0])
        finally:
            c.close()
    except sqlite3.Error:
        uv = -1
    return (str(p), st_.st_ino, st_.st_dev, uv)


class DataHubDB:
    """Wrapper fino sobre o SQLite com migração idempotente."""

    def __init__(self, db_path: Path | str | None = None, schema_path: Path | str = DEFAULT_SCHEMA):
        # Mantém o caminho local padrão, mas permite apontar para um volume persistente em produção.
        # Um caminho passado explicitamente pelo chamador sempre tem prioridade.
        configured_path = db_path if db_path is not None else (os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or str(DEFAULT_DB))
        self.db_path = Path(configured_path)
        self.schema_path = Path(schema_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # rodada 27f (LENTIDÃO): a migração rodava a CADA `DataHubDB()` — e o app cria vários (filtro de país em toda
        # consulta por time, Assistente, Scout). Com o processo de fundo gravando, cada uma esperava até 60 s × 4 + pausas
        # (≈ 5 min por tela). Agora: uma vez por processo e por arquivo; banco já pronto e ocupado → segue na hora.
        key = _migration_key(self.db_path)
        if key is not None and key in _MIGRATED:
            return
        with _MIG_LOCK:
            if key is not None and key in _MIGRATED:
                return
            self._migrate_patiently()
            k2 = _migration_key(self.db_path)
            if k2 is not None:
                _MIGRATED.add(k2)

    def _has_tables(self) -> bool:
        if not self.db_path.exists() or self.db_path.stat().st_size == 0:
            return False
        try:
            c = sqlite3.connect(str(self.db_path), timeout=5)
            try:
                return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='matches'").fetchone())
            finally:
                c.close()
        except sqlite3.Error:
            return False

    def _migrate_patiently(self, tries: int = 4, wait_s: float = 15.0) -> None:
        """Rodada 25c: outro processo do laboratório gravando (atualização automática, processo de fundo) fazia TODA
        ferramenta morrer com "database is locked" logo ao abrir o banco. Agora espera e tenta de novo; se o banco já
        tem as tabelas, segue sem migrar (as tabelas novas entram na próxima abertura livre)."""
        import time as _t

        ready = self._has_tables()
        if ready:
            tries = 1                       # banco já existe: migração leve só se estiver livre, sem esperar minutos
        for i in range(tries):
            try:
                self.migrate(quick=True) if ready else self.migrate()
                return
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    raise
                if i < tries - 1:
                    print(f"  banco ocupado por outro processo do laboratório — nova tentativa em {wait_s:.0f} s "
                          f"({i + 1}/{tries - 1})", flush=True)
                    _t.sleep(wait_s)
        try:
            with sqlite3.connect(str(self.db_path), timeout=5) as c:
                ok = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='matches'").fetchone()
        except sqlite3.Error:
            ok = None
        if not ok:
            raise sqlite3.OperationalError("database is locked (e o banco ainda não tem as tabelas)")
        if not ready:
            print("  banco continua ocupado: sigo sem a migração leve (só leitura das tabelas que já existem)", flush=True)

    # ------------------------------------------------------------------ infra
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        # rodada 14 (velocidade): no Windows abrir/fechar o arquivo do banco custa 10–30 ms (antivírus + WAL) e uma tela
        # fazia dezenas de consultas, cada uma com conexão nova. No banco PRINCIPAL a conexão fica aberta por thread e
        # é reaproveitada (mesmo comportamento: commit no fim, rollback em erro). Bancos temporários (testes) não.
        if _reuse_enabled(self.db_path):
            conn = _thread_conn(self)
            try:
                yield conn
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                raise
            return
        conn = self._open()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=60)
        conn.execute("PRAGMA busy_timeout = 60000;")
        # leitura e escrita ao mesmo tempo (a atualização automática grava enquanto a interface lê). Rodada 25c: um
        # ajuste que falha por banco ocupado não derruba mais a conexão inteira.
        for pragma in ("PRAGMA foreign_keys = ON;", "PRAGMA synchronous = NORMAL;",
                       "PRAGMA cache_size = -64000;",            # 64 MB de cache por conexão (o PC tem 16 GB)
                       "PRAGMA temp_store = MEMORY;",
                       "PRAGMA mmap_size = 268435456;",          # 256 MB mapeados: leituras grandes sem copiar
                       "PRAGMA journal_size_limit = 67108864;"):  # rodada 11: o arquivo de escrita volta a ≤ 64 MB
            try:
                conn.execute(pragma)
            except sqlite3.OperationalError:
                pass
        return conn

    def missing_speed_indexes(self) -> list:
        try:
            with self.connect() as conn:
                have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        except sqlite3.Error:
            return [n for n, _ in SPEED_INDEXES]
        return [n for n, _ in SPEED_INDEXES if n not in have]

    def ensure_speed_indexes(self, progress=None) -> list:
        """Cria (uma vez) os índices de velocidade; devolve os que foram criados agora."""
        say = progress or (lambda m: None)
        made = []
        for name, target in SPEED_INDEXES:
            if name not in self.missing_speed_indexes():
                continue
            say(f"criando {name} em {target}…")
            with self.connect() as conn:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")
            made.append(name)
        if made:
            say("atualizando as estatísticas do banco (ANALYZE)…")
            try:
                with self.connect() as conn:
                    conn.execute("PRAGMA optimize;")
            except sqlite3.Error:
                pass
        return made

    def migrate(self, quick: bool = False) -> None:
        """Aplica DDL leve e backfills legados uma única vez por versão do schema.
        quick=True (banco já existente): espera no máximo 3 s por outro gravador; ocupado → OperationalError e o
        chamador segue com as tabelas que já existem."""
        if quick:
            with self.connect() as conn:
                conn.execute("PRAGMA busy_timeout = 3000;")
            try:
                self._migrate_body()
            finally:
                with self.connect() as conn:
                    conn.execute("PRAGMA busy_timeout = 60000;")
            return
        self._migrate_body()

    def _migrate_body(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            if self.schema_path.exists():
                conn.executescript(self.schema_path.read_text(encoding="utf-8"))
            cols = {r[1] for r in conn.execute("PRAGMA table_info(matches)").fetchall()}
            for col, typ in MATCH_EXTRA_COLUMNS.items():
                if col not in cols:
                    conn.execute(f"ALTER TABLE matches ADD COLUMN {col} {typ}")
            conn.executescript(DATA_HUB_DDL)
            now = utc_now()
            conn.executemany(
                """INSERT OR IGNORE INTO source_state (source,state_key,state_value,updated_at)
                   VALUES ('cache',?,?,?)""",
                [("catalog_revision", "1", now), ("player_history_revision", "1", now)],
            )
        self._seed_demo_catalog()
        try:
            self._fix_levels()
        except Exception:
            pass
        with self.connect() as conn:
            schema_version = int((conn.execute("PRAGMA user_version").fetchone() or [0])[0])
            if schema_version < 27:
                # Backfill histórico caro: roda apenas na primeira abertura desta versão.
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
                if int((conn.execute("PRAGMA user_version").fetchone() or [0])[0]) >= 26:
                    conn.execute("PRAGMA user_version = 27")

    def _bump_cache_revision(self, key: str) -> None:
        """Incrementa revisão lógica sem ler/contar o catálogo ou o histórico."""
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO source_state (source,state_key,state_value,updated_at)
                   VALUES ('cache',?,'1',?)
                   ON CONFLICT(source,state_key) DO UPDATE SET
                     state_value=CAST(COALESCE(source_state.state_value,'0') AS INTEGER)+1,
                     updated_at=excluded.updated_at""",
                (key, utc_now()),
            )

    def _fix_levels(self) -> None:
        """BOXSCORE só quando há estatísticas de equipe; placar + gols/escalações = RESULT (corrige bases antigas)."""
        with self.connect() as conn:
            if (conn.execute("PRAGMA user_version").fetchone() or [0])[0] >= 26:
                return
            for old, new in (("shots_on_goal", "shots_on_target"), ("corner_kicks", "corners")):
                conn.execute("UPDATE OR IGNORE match_team_stats SET stat_key = ? WHERE stat_key = ?", (new, old))
            conn.execute(
                """UPDATE matches SET data_level = 'RESULT'
                   WHERE data_level = 'BOXSCORE' AND data_source IN ('openfootball', 'intl')
                     AND NOT EXISTS (SELECT 1 FROM match_team_stats s WHERE s.match_id = matches.match_id)""")
            conn.execute("PRAGMA user_version = 26")

    def reconcile_levels(self) -> int:
        """
        Rebaixa para RESULT partidas marcadas BOXSCORE sem nenhuma estatística de jogo de verdade (roda após cada
        sync). Gols no intervalo e afins não contam: sem chutes, posse, passes, escanteios, faltas, cartões ou xG
        a partida é "só placar" (ex.: temporadas antigas do football-data com só o placar do 1º tempo).
        """
        keys = ",".join(f"'{k}'" for k in MAIN_STATS)
        with self.connect() as conn:
            cur = conn.execute(
                f"""UPDATE matches SET data_level = 'RESULT'
                   WHERE data_level = 'BOXSCORE'
                     AND NOT EXISTS (SELECT 1 FROM match_team_stats s WHERE s.match_id = matches.match_id
                                     AND s.stat_key IN ({keys}))""")
            return cur.rowcount or 0

    def _seed_demo_catalog(self) -> None:
        """Garante no catálogo as partidas do pacote de demonstração offline (data/demo/)."""
        demo = Path("data/demo/statsbomb_demo_matches.json")
        if not demo.exists():
            return
        try:
            from src.data_hub.sources.statsbomb import StatsBombProvider

            raw = json.loads(demo.read_text(encoding="utf-8"))
            recs = [r for r in StatsBombProvider.parse_matches(raw, {}) if self.get_match(r["match_id"]) is None]
            if recs:
                self.upsert_matches(recs)
        except Exception:
            pass

    # --------------------------------------------------------------- catálogo
    def upsert_matches(self, records: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        """Insere/atualiza partidas sem nunca rebaixar o nível de dado já existente."""
        rank = {DataLevel.RESULT: 1, DataLevel.BOXSCORE: 2, DataLevel.EVENTS: 3,
                DataLevel.SIMULATED: 0, DataLevel.UPLOAD: 0}
        added = updated = 0
        now = utc_now()
        from src.data_hub.quality import validate_matches

        records, rejected, _ = validate_matches(list(records))   # placar negativo, equipe vazia, data impossível
        if rejected:
            from src.data_hub.net import log as _log

            for b in rejected[:50]:
                _log(str(b.get("fonte") or "catalogo"), f"partida {b['match_id']} rejeitada: {b['motivo']}")
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
        if added or updated:
            self._touched()
        return {"added": added, "updated": updated, "rejected": len(rejected)}

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
            df = pd.read_sql_query(sql, conn, params=params)
        from src.data_hub.gender import gender_series

        df["genero"] = gender_series(df)
        return df

    # ------------------------------------------------------------------ rodada 22: catálogo único em memória
    _CAT: Dict[str, Dict[str, Any]] = {}
    CAT_FULL_RELOAD_S = 6 * 3600

    def catalog_memo(self, version: str) -> pd.DataFrame:
        """
        O catálogo inteiro (todas as partidas, com `genero`) UMA vez por processo. Antes cada filtro diferente relia as
        ~300–440 mil partidas do SQLite (2–3 s) e o cache do Streamlit copiava o DataFrame inteiro (100+ MB) a cada uso.
        Quando a versão muda (jogos novos), lê só as linhas gravadas depois da última leitura (`last_synced`) e confere o
        nível de dado de todas (2 colunas) — releitura completa no máximo a cada 6 h ou se algo não fechar.
        NÃO altere o DataFrame devolvido (use `catalog_view`, que devolve uma cópia rasa).
        """
        import threading
        import time as _t

        key = str(self.db_path)
        lock = DataHubDB._CAT.setdefault("__lock__", {"l": threading.Lock()})["l"]
        with lock:
            m = DataHubDB._CAT.get(key)
            if m is not None and m["version"] == version:
                return m["df"]
            now = _t.time()
            df = None
            if m is None:                                     # app abrindo: cópia em disco (parquet) + o que mudou
                m = self._catalog_from_disk()
            if m is not None and now - m["full_at"] < self.CAT_FULL_RELOAD_S:
                try:
                    df = self._catalog_incremental(m["df"], m["synced"])
                except Exception:
                    df = None
            if df is None:
                df = self.catalog()
                full_at = now
            else:
                full_at = m["full_at"]
            synced = str(df["last_synced"].dropna().max() or "") if "last_synced" in df and len(df) else ""
            DataHubDB._CAT[key] = {"version": version, "df": df, "synced": synced, "full_at": full_at, "views": {}}
            if full_at == now:
                self._catalog_to_disk(df, synced, full_at)
            return df

    def _catalog_disk_path(self) -> Path:
        import hashlib

        tag = hashlib.sha1(str(Path(self.db_path).resolve()).encode()).hexdigest()[:10]
        return Path("data/processed") / f"catalogo_{tag}.parquet"

    def _catalog_from_disk(self) -> Optional[Dict[str, Any]]:
        """Rodada 22: ler 440 mil partidas do SQLite custa ~5–8 s no PC; do parquet, < 1 s. Depois só o que mudou."""
        import time as _t

        if os.getenv("TIL_CATALOGO_DISCO", "1").strip() in ("0", "false"):
            return None
        p = self._catalog_disk_path()
        try:
            age = _t.time() - p.stat().st_mtime
            if age > self.CAT_FULL_RELOAD_S:
                return None
            df = pd.read_parquet(p)
            synced = str(df["last_synced"].dropna().max() or "") if len(df) else ""
            return {"version": None, "df": df, "synced": synced, "full_at": _t.time() - age, "views": {}}
        except Exception:
            return None

    def _catalog_to_disk(self, df: pd.DataFrame, synced: str, full_at: float) -> None:
        if os.getenv("TIL_CATALOGO_DISCO", "1").strip() in ("0", "false"):
            return
        import threading

        def _save():
            try:
                p = self._catalog_disk_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".tmp")
                df.to_parquet(tmp, index=False)
                os.replace(tmp, p)
            except Exception:
                pass
        threading.Thread(target=_save, name="til-catalogo-disco", daemon=True).start()

    def _catalog_incremental(self, old: pd.DataFrame, synced: str) -> Optional[pd.DataFrame]:
        from src.data_hub.gender import gender_series

        with self.connect() as conn:
            new = pd.read_sql_query("SELECT * FROM matches WHERE last_synced >= ?", conn, params=(synced or "",))
            lv = pd.read_sql_query("SELECT match_id, data_level FROM matches", conn)
        df = old
        need_sort = False
        if len(new):
            new["genero"] = gender_series(new)
            new = new.sort_values(["match_date", "match_id"], ascending=False)
            rest = df[~df["match_id"].isin(new["match_id"])]
            # jogos novos costumam ser os mais recentes: basta empilhar por cima (ordenar 300 mil linhas custa ~0,5 s)
            need_sort = bool(len(rest)) and str(new["match_date"].iloc[-1]) < str(rest["match_date"].iloc[0])
            df = pd.concat([new, rest], ignore_index=True)
        if len(df) != len(lv):
            df = df[df["match_id"].isin(lv["match_id"])]
            if len(df) != len(lv):
                return None                                   # algo não fechou: releitura completa
        want = lv.set_index("match_id")["data_level"]
        now_lv = df["match_id"].map(want)
        diff = now_lv.notna() & (now_lv.values != df["data_level"].values)
        if diff.any():                                        # nível promovido por outra gravação (sem last_synced)
            df = df.copy()
            df.loc[diff, "data_level"] = now_lv[diff]
        if need_sort:
            df = df.sort_values(["match_date", "match_id"], ascending=False, ignore_index=True)
        return df.reset_index(drop=True)

    def catalog_view(self, version: str, key: Any, build) -> pd.DataFrame:
        """Recorte memorizado do catálogo (por versão + `key`); `build(df_completo)` devolve o recorte. Cópia rasa:
        com o pandas 3 (copy-on-write) quem recebe pode criar/alterar colunas sem estragar o original."""
        base = self.catalog_memo(version)
        m = DataHubDB._CAT.get(str(self.db_path)) or {}
        views = m.setdefault("views", {})
        hit = views.get(key)
        if hit is None:
            hit = build(base)
            if len(views) >= 24:
                views.pop(next(iter(views)))
            views[key] = hit
        return hit.copy(deep=False)

    def catalog_version(self) -> str:
        """
        Chave de cache da interface: muda SÓ quando o catálogo muda de verdade (partidas novas ou nível de dado
        promovido). Antes incluía o relógio e, a cada 10 min, o app relia o catálogo inteiro do banco.
        """
        with self.connect() as conn:
            row = conn.execute(
                "SELECT state_value FROM source_state WHERE source='cache' AND state_key='catalog_revision'"
            ).fetchone()
            if row and row[0] is not None:
                return str(row[0])
            n, rich = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN data_level IN ('EVENTS','BOXSCORE') THEN 1 ELSE 0 END) FROM matches"
            ).fetchone()
        return f"{n}:{rich or 0}"

    _ver_memo: Dict[str, Any] = {}

    def stable_version(self, settle_s: float = 600.0, probe_s: float = 20.0, force: bool = False) -> str:
        """
        Versão do catálogo para a INTERFACE. Enquanto uma sincronização grava, o catálogo muda a cada segundo e,
        com catalog_version() direto, toda tela relia ~300 mil partidas e reconstruía os índices a cada clique
        (minutos por página). Aqui: o banco é consultado no máximo a cada `probe_s` e uma versão nova só é
        adotada `settle_s` depois da anterior (ou quando force=True — botão "atualizar"). O app nunca fica preso
        num catálogo velho: no pior caso, vê as partidas novas 10 minutos depois.
        """
        import time as _t

        key = str(self.db_path)
        m = DataHubDB._ver_memo.setdefault(key, {"adopted": None, "at": 0.0, "probed": 0.0, "latest": None})
        now = _t.time()
        if m["adopted"] is not None and not force and _frozen() and now - m["at"] < FROZEN_SETTLE_S:
            # rodada 19: congelado — o catálogo não muda na apresentação; rodada 22: mas no máximo por 3 h (antes nunca
            # mudava e os jogos de ontem não apareciam para quem usa o link todo dia)
            return m["adopted"]
        if force or m["adopted"] is None or now - m["probed"] >= probe_s:
            try:
                m["latest"] = self.catalog_version()
            except Exception:
                m["latest"] = m["latest"] or m["adopted"] or "0:0"
            m["probed"] = now
        if force or m["adopted"] is None or (m["latest"] != m["adopted"] and now - m["at"] >= settle_s):
            m["adopted"], m["at"] = m["latest"], now
        return m["adopted"]

    _team_memo: Dict[str, Any] = {}

    def team_version(self, names: Iterable[str], ttl_s: float = 60.0) -> str:
        """rodada 14: versão POR TIME para os caches das telas pesadas — muda só quando chega jogo/estatística nova
        desse time (ou na virada do dia). A versão geral mudava a cada 10 min durante as atualizações e jogava fora o
        cache de TODAS as telas, mesmo de times que não ganharam nenhum dado novo."""
        import time as _t

        ns = sorted({str(n) for n in names if n})
        if not ns:
            return f"t:none:{'congelado' if _frozen() else datetime.now().date()}"
        key = f"{self.db_path}|{'|'.join(ns)}"
        hit = DataHubDB._team_memo.get(key)
        now = _t.time()
        if hit and now - hit[1] < ttl_s:
            return hit[0]
        ph = ",".join("?" * len(ns))
        try:
            with self.connect() as conn:
                r = conn.execute(f"SELECT COUNT(*), MAX(match_date), SUM(CASE WHEN data_level IN ('EVENTS','BOXSCORE') "
                                 f"THEN 1 ELSE 0 END) FROM matches WHERE home_team_name IN ({ph}) OR away_team_name IN ({ph})",
                                 ns + ns).fetchone()
            v = f"t:{r[0]}:{r[1]}:{r[2]}:{'congelado' if _frozen() else datetime.now().date()}"
        except Exception:
            v = f"t:err:{datetime.now().date()}"
        DataHubDB._team_memo[key] = (v, now)
        return v

    def _touched(self) -> None:
        """Gravação feita pela própria tela (busca remota, upload, botão): a interface vê na hora. A atualização
        automática (thread til-autosync) e as sincronizações em outro terminal seguem o ritmo de stable_version."""
        import threading

        # rodada 7: QUALQUER trabalho de fundo (til-fotmob, til-openplay-prefetch, til-ao-vivo…) e o processo de
        # fundo seguem o ritmo de stable_version — antes só til-autosync, e cada jogo da FotMob fazia a tela reler
        # o catálogo inteiro no clique seguinte
        if not threading.current_thread().name.startswith("til-") and os.environ.get("TIL_IN_WORKER") != "1":
            DataHubDB._ver_memo.pop(str(self.db_path), None)

    def has_pending_update(self) -> bool:
        m = DataHubDB._ver_memo.get(str(self.db_path)) or {}
        return bool(m.get("latest") and m.get("adopted") and m["latest"] != m["adopted"])

    def level_counts(self) -> Dict[str, int]:
        with self.connect() as conn:
            return {str(k): int(v) for k, v in conn.execute("SELECT data_level, COUNT(*) FROM matches GROUP BY 1")}

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
            from src.data_hub.quality import clean_timeline

            for e in clean_timeline(box.get("timeline", [])):
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
                     p.get("rating"), json.dumps(p.get("stats") or {}, ensure_ascii=False, separators=(",", ":"))),
                )
        self._bump_cache_revision("player_history_revision")

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
