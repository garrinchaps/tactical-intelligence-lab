"""
Atualização automática da base enquanto o app está aberto.

* A cada AUTO_SYNC_HOURS (padrão 3 h): jogos recentes — football-data.co.uk (temporada atual), API-Football,
  football-data.org e ESPN (as que estiverem habilitadas no .env) — e o boxscore dos jogos novos.
* A cada 24 h: catálogos do StatsBomb e da Wyscout, Transfermarkt (valores de mercado), Understat (xG e
  finalizações), API-Futebol e Base dos Dados (se configuradas) e a reconstrução da camada unificada de IDs.

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
QUICK = ["fdcouk", "open_matchday", "api_football", "football_data", "espn"]
DAILY = ["espn_elencos", "statsbomb", "wyscout", "openfootball", "brasileirao", "open_sources", "transfermarkt", "understat", "api_futebol", "basedosdados", "simonetti", "lake", "estatisticas_brasil"]


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


# ------------------------------------------------------------------ FotMob contínua (rodada 5, pedido do usuário)
_fm: Dict[str, Any] = {"running": False, "baixados": 0, "pendentes": None, "fase": "", "ultimo": None,
                               "ultima_regua": None, "regua_status": None, "erro": None}


def _refresh_rating_references(svc) -> None:
    """Atualiza diariamente as réguas comuns de desempenho por posição após novos dados FotMob/eventos."""
    from src.data_hub import sync_policy as P

    last = P.last_synced(svc.db, "ratings", "_referencias_diarias")
    if last is not None and datetime.now(timezone.utc) - last < timedelta(hours=24):
        return
    box_n = event_n = 0
    errors = []
    try:
        from src.analytics.rating_box import build_reference as build_box_reference

        box_n = build_box_reference(svc.db, limit=600)
    except Exception as exc:
        errors.append(f"FotMob: {type(exc).__name__}: {exc}")
    try:
        from src.analytics.rating_v2 import build_reference_from_db

        event_n = build_reference_from_db(limit=300, progress=lambda msg: None)
    except Exception as exc:
        errors.append(f"eventos: {type(exc).__name__}: {exc}")
    P.mark_synced(svc.db, "ratings", "_referencias_diarias")
    _fm["ultima_regua"] = datetime.now(timezone.utc)
    _fm["regua_status"] = f"régua atualizada: {box_n} atuações FotMob e {event_n} atuações com eventos"
    if errors:
        _fm["regua_status"] += " · " + " | ".join(errors)[:180]


def fotmob_enabled() -> bool:
    """Ligada por padrão; ENABLE_FOTMOB=false no .env desliga."""
    return os.getenv("ENABLE_FOTMOB", "true").strip().lower() not in ("0", "false", "nao", "não", "no")


def _fotmob_loop() -> None:
    """
    Abastece a base sozinha enquanto o app está aberto, um pedido a cada ~0,7 s, sem travar a tela:
      1. uma vez por dia: calendário e resultados da temporada atual de todas as competições (e, na 1ª vez, as
         temporadas anteriores — FOTMOB_TEMPORADAS, padrão 2; temporada passada já baixada não é pedida de novo);
      2. detalhes dos jogos dos últimos 10 dias (estatísticas, escalação, números por jogador, chutes);
      3. o histórico em lotes de 300, Brasil e Europa principal primeiro, do mais novo ao mais velho;
      4. quando não falta nada, dorme 30 min e confere de novo.
    """
    import time

    from src.data_hub import sync_policy as P
    from src.data_hub.service import MatchDataService

    try:
        svc = MatchDataService()
        fm = svc.fotmob
        while enabled() and fotmob_enabled():
            try:
                last = P.last_synced(svc.db, "fotmob", "_temporada_diaria")
                if last is None or datetime.now(timezone.utc) - last >= timedelta(hours=24):
                    _fm["fase"] = "calendário e resultados"
                    try:
                        back = max(0, min(int(os.getenv("FOTMOB_TEMPORADAS", "2")), 5))
                    except ValueError:
                        back = 2
                    fm.sync_seasons(None, seasons_back=back)
                    P.mark_synced(svc.db, "fotmob", "_temporada_diaria")
                _fm["fase"] = "jogos dos últimos 10 dias"
                r1 = fm.fetch_details(None, since=(datetime.now().date() - timedelta(days=10)).isoformat(), limit=200,
                                      stop=lambda: not enabled())
                _fm["fase"] = "histórico"
                r2 = fm.fetch_details(None, since=f"{datetime.now().year - 5}-01-01", limit=300, stop=lambda: not enabled())
                _fm["baixados"] += r1["detalhes"] + r2["detalhes"]
                _fm["pendentes"] = fm.pending()
                _fm["fase"] = "atualizando réguas de desempenho"
                _refresh_rating_references(svc)
                _fm["ultimo"] = datetime.now(timezone.utc)
                _fm["erro"] = None
                if r1["detalhes"] + r2["detalhes"] == 0:
                    _fm["fase"] = "em dia"
                    time.sleep(30 * 60)
                else:
                    time.sleep(5)
            except Exception as exc:            # sem internet, site fora: tenta de novo em 10 min, nunca derruba o app
                _fm["erro"] = f"{type(exc).__name__}: {exc}"
                time.sleep(10 * 60)
    finally:
        _fm["running"] = False


def fotmob_status() -> str:
    if not fotmob_enabled():
        return ""
    if _fm.get("erro"):
        return f"FotMob: tentando de novo em instantes ({_fm['erro'][:60]})"
    if not _fm.get("running"):
        return ""
    p = _fm.get("pendentes")
    status = (f"⚡ FotMob abastecendo a base ({_fm.get('fase', '')}): {_fm['baixados']} jogos com detalhes nesta sessão"
              + (f" · faltam {p}" if p is not None else ""))
    return status + (f" · {_fm['regua_status']}" if _fm.get("regua_status") else "")


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


_live = {"running": False, "last": None, "ao_vivo": 0, "ligas": []}
LIVE_CHECK_MIN = 15          # sem jogo ao vivo: confere a cada 15 min; com jogo ao vivo: a cada 1 min


def _live_loop() -> None:
    """B2: enquanto houver jogo ao vivo (ESPN), atualiza o placar a cada minuto; senão, confere a cada 15 min."""
    import time

    from src.data_hub.service import MatchDataService

    try:
        svc = MatchDataService()
        if not svc.espn.enabled:
            return
        while enabled():
            try:                                     # ao vivo: só as ligas com jogo rolando; senão, varredura completa
                r = svc.espn.live_tick(_live["ligas"] or None)
                _live.update(last=datetime.now(timezone.utc), ao_vivo=r.get("ao_vivo", 0),
                             ligas=r.get("ligas_ao_vivo", []))
            except Exception:
                pass
            time.sleep(60 if _live["ao_vivo"] else LIVE_CHECK_MIN * 60)
    finally:
        _live["running"] = False


def ensure_started(db) -> Dict[str, Any]:
    """Dispara a atualização em segundo plano se algo estiver vencido. Seguro chamar a cada recarga da página."""
    if not enabled():
        return {**_state, "enabled": False, "due": []}
    with _lock:
        if not _live["running"] and os.getenv("AUTO_SYNC_LIVE", "1").strip() not in ("0", "false"):
            _live["running"] = True
            threading.Thread(target=_live_loop, daemon=True, name="til-ao-vivo").start()
        if not _fm["running"] and fotmob_enabled():
            _fm["running"] = True
            threading.Thread(target=_fotmob_loop, daemon=True, name="til-fotmob").start()
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
