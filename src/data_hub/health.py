"""
Saúde das fontes (v36, itens G1/G2): status, última sincronização, partidas coletadas por profundidade, cota do dia,
erros recentes — e ações manuais que rodam em SEGUNDO PLANO (a interface nunca trava esperando).
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

QUOTAS = {"api_football": 100}          # cota diária conhecida (plano grátis)
LOG_PATH = Path("data/sync_log.txt")
_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _parse(ts) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def source_health(db, now: Optional[datetime] = None) -> pd.DataFrame:
    now = now or datetime.now(timezone.utc)
    with db.connect() as conn:
        runs = pd.read_sql_query("SELECT source, started_at, finished_at, status, matches_added, matches_updated, message "
                                 "FROM sync_runs ORDER BY id DESC LIMIT 2000", conn)
        lv = pd.read_sql_query("SELECT data_source AS source, data_level, COUNT(*) AS n FROM matches "
                               "GROUP BY data_source, data_level", conn)
        try:
            use = pd.read_sql_query("SELECT provider AS source, requests FROM api_usage WHERE usage_date = ?", conn,
                                    params=(now.date().isoformat(),))
        except Exception:
            use = pd.DataFrame(columns=["source", "requests"])
    sources = sorted(set(runs["source"]) | set(lv["source"].dropna()))
    rows = []
    for s in sources:
        r = runs[runs["source"] == s]
        if r.empty and s in JOBS_OF:                     # rodada 19: partidas gravadas por tarefas de outro nome
            r = runs[runs["source"].isin(JOBS_OF[s])]
        last = r.iloc[0] if not r.empty else None
        when = _parse(last["finished_at"] or last["started_at"]) if last is not None else None
        ok_recent = r.head(10)["status"].eq("OK").sum() if not r.empty else 0
        st = (last["status"] if last is not None else None) or ""
        if s == "simulated":
            status = "🧪 exemplos internos (fora das análises reais)"
        elif last is None:
            status = "— nunca sincronizada"
        elif st == "DESATIVADA":
            status = "⏸ desativada"
        elif st == "OK" and when and now - when <= timedelta(days=3):
            status = "✅ funcionando"
        elif st == "OK":
            status = "🕒 desatualizada"
        else:
            status = "⚠️ com falhas"
        l = lv[lv["source"] == s].set_index("data_level")["n"]
        used = int(use.loc[use["source"] == s, "requests"].sum()) if not use.empty else 0
        quota = QUOTAS.get(s)
        errs = r[~r["status"].isin(["OK", "DESATIVADA"])].head(1)
        rows.append({"fonte": s, "status": status,
                     "última sincronização": when.astimezone().strftime("%d/%m %H:%M") if when else "—",
                     "partidas": int(l.sum()), "com lances": int(l.get("EVENTS", 0)),
                     "com estatísticas": int(l.get("BOXSCORE", 0)), "só placar": int(l.get("RESULT", 0)),
                     "cota hoje": f"{used}/{quota}" if quota else (str(used) if used else "—"),
                     "sucessos (últimas 10)": f"{ok_recent}/{min(len(r), 10)}" if not r.empty else "—",
                     "erro mais recente": _err_text(errs, st)})
    return pd.DataFrame(rows)


# rodada 19: fonte das PARTIDAS → tarefas de sincronização que as gravam
JOBS_OF = {"fotmob": ["fotmob_jogos", "fotmob_temporada", "fotmob_recentes", "fotmob_tudo"],
           "intl": ["open_sources"]}


def _err_text(errs: pd.DataFrame, last_status: str) -> str:
    """Erro com a data; se a última execução deu certo, avisa que é antigo (já resolvido)."""
    if errs.empty:
        return ""
    e = errs.iloc[0]
    when = _parse(e.get("finished_at") or e.get("started_at"))
    tag = when.astimezone().strftime("%d/%m %H:%M") if when else "?"
    msg = str(e.get("message") or "").replace("\n", " ")[:140]
    return (f"[antigo, {tag} — depois funcionou] " if last_status == "OK" else f"[{tag}] ") + msg


def start_job(name: str, fn: Callable[[Callable[[str], None]], Any]) -> bool:
    """Roda `fn(say)` numa thread; devolve False se já houver um trabalho com esse nome rodando."""
    with _lock:
        if _jobs.get(name, {}).get("running"):
            return False
        job = {"running": True, "log": [], "started": datetime.now(timezone.utc), "result": None, "error": None}
        _jobs[name] = job

    def run():
        try:
            job["result"] = fn(job["log"].append)
        except Exception as exc:
            job["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            job["running"] = False
            job["finished"] = datetime.now(timezone.utc)
    threading.Thread(target=run, daemon=True, name=f"til-job-{name}").start()
    return True


def jobs() -> Dict[str, Dict[str, Any]]:
    return dict(_jobs)


def tail_log(n: int = 60, path: Path = LOG_PATH) -> List[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except Exception:
        return []
