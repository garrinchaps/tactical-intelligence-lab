"""
Atualização automática da base enquanto o app está aberto.

* A cada AUTO_SYNC_HOURS (padrão 3 h): jogos recentes — football-data.co.uk (temporada atual), API-Football,
  football-data.org e ESPN (as que estiverem habilitadas no .env) — e o boxscore dos jogos novos.
* A cada 24 h: catálogos do StatsBomb e da Wyscout (novas competições/temporadas publicadas).

Roda numa thread em segundo plano, uma de cada vez, sem travar a interface. Com o app fechado, use a tarefa
agendada do Windows (scripts/agendar_atualizacao.ps1). Desligar: AUTO_SYNC=0 no .env.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
_state: Dict[str, Any] = {"running": False, "last_finished": None, "last_attempt": None, "last_log": [], "last_error": None}
RETRY_MINUTES = 30   # se a última tentativa falhou (ex.: sem internet), espera antes de tentar de novo
QUICK = ["fdcouk", "api_football", "football_data", "espn"]
DAILY = ["statsbomb", "wyscout"]


def enabled() -> bool:
    return os.getenv("AUTO_SYNC", "1").strip() not in ("0", "false", "False", "nao", "não")


def interval_hours() -> float:
    try:
        return max(float(os.getenv("AUTO_SYNC_HOURS", "3")), 0.5)
    except ValueError:
        return 3.0


def _last_ok(db, sources: List[str]) -> Optional[datetime]:
    """Horário (UTC) da última sincronização OK de qualquer uma das fontes."""
    h = db.sync_history(limit=200)
    if h.empty:
        return None
    h = h[(h["source"].isin(sources)) & (h["status"].isin(["OK", "DESATIVADA"]))]
    if h.empty:
        return None
    t = str(h["finished_at"].dropna().max() or h["started_at"].max())
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def due(db, now: Optional[datetime] = None) -> List[str]:
    """Quais fontes estão vencidas agora."""
    now = now or datetime.now(timezone.utc)
    out: List[str] = []
    q = _last_ok(db, QUICK)
    if q is None or now - q >= timedelta(hours=interval_hours()):
        out += QUICK
    d = _last_ok(db, DAILY)
    if d is None or now - d >= timedelta(hours=24):
        out += DAILY
    return out


def _run(sources: List[str]) -> None:
    from src.data_hub.service import MatchDataService
    from src.data_hub.sync import run_sync

    log: List[str] = []
    try:
        run_sync(sources, days_back=3, prefetch_events=0, service=MatchDataService(), progress=log.append,
                 seasons_back=0, prefetch_boxscores=30)
        _state["last_error"] = None
    except Exception as exc:  # nunca derruba o app
        _state["last_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        _state.update(running=False, last_finished=datetime.now(timezone.utc), last_log=log[-30:])


def ensure_started(db) -> Dict[str, Any]:
    """Dispara a atualização em segundo plano se algo estiver vencido. Seguro chamar a cada recarga da página."""
    if not enabled():
        return {**_state, "enabled": False, "due": []}
    with _lock:
        recent = _state["last_attempt"] and datetime.now(timezone.utc) - _state["last_attempt"] < timedelta(minutes=RETRY_MINUTES)
        if not _state["running"] and not recent:
            pending = due(db)
            if pending:
                _state["running"] = True
                _state["last_attempt"] = datetime.now(timezone.utc)
                threading.Thread(target=_run, args=(pending,), daemon=True, name="til-autosync").start()
                _state["due"] = pending
    return {**_state, "enabled": True, "next_quick": _next(db)}


def _next(db) -> Optional[datetime]:
    q = _last_ok(db, QUICK)
    return q + timedelta(hours=interval_hours()) if q else None


def status_text(st_: Dict[str, Any]) -> str:
    if not st_.get("enabled", True):
        return "Atualização automática desligada (AUTO_SYNC=0)."
    if st_.get("running"):
        return "🔄 Atualizando a base em segundo plano (jogos recentes)…"
    nxt = st_.get("next_quick")
    local = lambda d: d.astimezone().strftime("%d/%m %H:%M")
    if nxt:
        return f"🔄 Base atualizada automaticamente a cada {interval_hours():g} h · próxima: {local(nxt)}"
    return "🔄 Atualização automática ativa."
