"""
Rodada 16 — monitor de velocidade do app.

Mede o tempo de CADA tela aberta e das funções pesadas marcadas com @timed, guarda num arquivo local
(data/perf.jsonl, até 5 mil linhas — o mais antigo sai) e mostra nos Bastidores: mediana, 90% e pior tempo por tela e
por função, com alerta para o que passa da meta. A barra do topo mostra quanto a tela atual levou.
"""

from __future__ import annotations

import functools
import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List

PATH = Path("data/perf.jsonl")
MAX_LINES = 5000
GOAL_PAGE_S = 2.0          # meta por tela (com cache quente)
GOAL_FUNC_S = 1.0
_LOCK = threading.Lock()
_RECENT: deque = deque(maxlen=400)


def record(kind: str, name: str, seconds: float, **extra: Any) -> None:
    row = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "tipo": kind, "nome": name, "s": round(float(seconds), 3), **extra}
    _RECENT.append(row)
    try:
        with _LOCK:
            PATH.parent.mkdir(parents=True, exist_ok=True)
            with PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if PATH.stat().st_size > 900_000:                 # mantém o arquivo pequeno
                lines = PATH.read_text(encoding="utf-8").splitlines()[-MAX_LINES:]
                PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def timed(name: str | None = None) -> Callable:
    """Decorador: mede a função (inclusive quando vem do cache — aí fica bem rápido, o que também é informação)."""
    def deco(fn: Callable) -> Callable:
        label = name or f"{fn.__module__.split('.')[-1]}.{fn.__name__}"

        @functools.wraps(fn)
        def wrap(*a, **k):
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                record("funcao", label, time.perf_counter() - t0)
        if hasattr(fn, "clear"):                      # funções com cache do Streamlit continuam limpáveis (.clear())
            wrap.clear = fn.clear
        return wrap
    return deco


def read(last: int = 5000) -> List[Dict[str, Any]]:
    try:
        lines = PATH.read_text(encoding="utf-8").splitlines()[-last:]
    except OSError:
        return list(_RECENT)
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def summary(rows: List[Dict[str, Any]] | None = None):
    import pandas as pd

    rows = rows if rows is not None else read()
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    g = d.groupby(["tipo", "nome"])["s"]
    out = pd.DataFrame({"vezes": g.size(), "mediana_s": g.median().round(2), "p90_s": g.quantile(.9).round(2),
                        "pior_s": g.max().round(2), "ultima_s": g.last().round(2)}).reset_index()
    goal = out["tipo"].map({"tela": GOAL_PAGE_S}).fillna(GOAL_FUNC_S)
    out["situação"] = ["✅ dentro da meta" if p <= gl else ("⚠️ lenta às vezes" if m <= gl else "🔴 lenta")
                       for p, m, gl in zip(out["p90_s"], out["mediana_s"], goal)]
    return out.sort_values(["tipo", "p90_s"], ascending=[True, False])
