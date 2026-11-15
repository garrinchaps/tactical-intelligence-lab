"""
Política de atualização (v36, item B2) — decide O QUE buscar e QUANDO, sem varrer tudo de novo.

* Incremental por competição: `competition_sync_state` guarda `last_synced_at`; a próxima busca começa 2 dias
  antes dele (para pegar jogos adiados), nunca a temporada inteira.
* Partida AO VIVO: atualizada a cada minuto (quando a fonte permite — hoje a ESPN pública).
* Partida ENCERRADA: recebe UMA consolidação final (placar + estatísticas) e é CONGELADA (`frozen_matches`):
  não é baixada de novo.
* Partida FUTURA (fixture): calendário atualizado a cada 3 h; nunca se busca estatística de jogo que não aconteceu.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional

LIVE_STATUS = {"LIVE", "IN_PLAY", "1H", "2H", "HT", "ET", "P", "STATUS_IN_PROGRESS", "STATUS_HALFTIME",
               "STATUS_FIRST_HALF", "STATUS_SECOND_HALF", "STATUS_EXTRA_TIME"}
FINISHED_STATUS = {"FT", "AET", "PEN", "FINISHED", "STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_AET", "STATUS_FINAL_PEN"}
INTERVAL_S = {"ao_vivo": 60, "futura": 3 * 3600, "encerrada": 0, "congelada": None}
OVERLAP_DAYS = 2
MAX_WINDOW_DAYS = 30

DDL = """
CREATE TABLE IF NOT EXISTS competition_sync_state (source TEXT, competition TEXT, last_synced_at TEXT,
    PRIMARY KEY (source, competition));
CREATE TABLE IF NOT EXISTS frozen_matches (match_id INTEGER PRIMARY KEY, frozen_at TEXT);
"""


def kind(status: Optional[str], frozen: bool = False) -> str:
    s = str(status or "").upper()
    if frozen:
        return "congelada"
    if s in LIVE_STATUS:
        return "ao_vivo"
    if s in FINISHED_STATUS:
        return "encerrada"
    return "futura"


def fetch_stats(kind_: str) -> bool:
    """Estatística/escalação só para jogo ao vivo ou recém-encerrado (nunca para fixture nem congelado)."""
    return kind_ in ("ao_vivo", "encerrada")


def _ensure(db) -> None:
    with db.connect() as conn:
        conn.executescript(DDL)


def last_synced(db, source: str, competition: str) -> Optional[datetime]:
    _ensure(db)
    with db.connect() as conn:
        r = conn.execute("SELECT last_synced_at FROM competition_sync_state WHERE source=? AND competition=?",
                         (source, competition)).fetchone()
    if not r or not r[0]:
        return None
    dt = datetime.fromisoformat(r[0])
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def mark_synced(db, source: str, competition: str, when: Optional[datetime] = None) -> None:
    _ensure(db)
    when = when or datetime.now(timezone.utc)
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO competition_sync_state (source, competition, last_synced_at) VALUES (?, ?, ?)",
                     (source, competition, when.isoformat(timespec="seconds")))


def window(db, source: str, competition: str, today: Optional[date] = None, default_days: int = 3):
    """Janela incremental [início, hoje]: do último sync − 2 dias (máx. 30 dias); sem histórico, `default_days`."""
    today = today or date.today()
    last = last_synced(db, source, competition)
    if last is None:
        return today - timedelta(days=default_days), today
    start = max(last.date() - timedelta(days=OVERLAP_DAYS), today - timedelta(days=MAX_WINDOW_DAYS))
    return min(start, today), today


def is_frozen(db, match_id: int) -> bool:
    _ensure(db)
    with db.connect() as conn:
        return conn.execute("SELECT 1 FROM frozen_matches WHERE match_id=?", (int(match_id),)).fetchone() is not None


def freeze(db, match_ids: Iterable[int]) -> int:
    """Congela partidas encerradas já consolidadas: não são buscadas de novo."""
    _ensure(db)
    ids = [int(m) for m in match_ids]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as conn:
        conn.executemany("INSERT OR IGNORE INTO frozen_matches (match_id, frozen_at) VALUES (?, ?)", [(m, now) for m in ids])
    return len(ids)


def due_fixtures(db, source: str, competitions: List[str], now: Optional[datetime] = None) -> List[str]:
    """Competições cujo calendário (fixtures) venceu: última atualização há 3 h ou mais."""
    now = now or datetime.now(timezone.utc)
    out = []
    for c in competitions:
        last = last_synced(db, source, c)
        if last is None or (now - last).total_seconds() >= INTERVAL_S["futura"]:
            out.append(c)
    return out
