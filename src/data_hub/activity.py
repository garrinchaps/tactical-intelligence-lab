"""
Rodada 11 — "modo leve" enquanto você usa o app.

A tela marca um batimento em `data/ui_active` (no máximo 1 gravação a cada 10 s). O processo de fundo consulta esse
batimento antes de cada lote pesado (OpenPlay, FotMob histórico, réguas, fotografia do Scout, jogo típico): se a tela
foi usada no último minuto e meio, ele ESPERA. Assim o banco não fica sendo gravado sem parar enquanto você clica — a
causa da lentidão geral (o arquivo de escrita do SQLite inchava e toda leitura da tela ficava lenta).
Desligar: TIL_MODO_LEVE=0 no .env.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

PATH = Path("data/ui_active")
_last_touch = {"t": 0.0}


def enabled() -> bool:
    return os.getenv("TIL_MODO_LEVE", "1").strip().lower() not in ("0", "false", "nao", "não")


def touch() -> None:
    """Chamado pela tela a cada recarga; barato (grava no máximo a cada 10 s)."""
    now = time.time()
    if now - _last_touch["t"] < 10:
        return
    _last_touch["t"] = now
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(str(now), encoding="utf-8")
    except Exception:
        pass


def ui_active(window_s: float = 90) -> bool:
    if not enabled():
        return False
    try:
        return time.time() - float(PATH.read_text(encoding="utf-8").strip() or 0) < window_s
    except Exception:
        return False


def wait_idle(state: dict | None = None, key: str = "fase", max_wait_s: float = 3600, step_s: float = 15) -> None:
    """Espera a tela ficar parada (até `max_wait_s`) antes de um lote pesado."""
    t0 = time.time()
    shown = False
    while ui_active() and time.time() - t0 < max_wait_s:
        if state is not None and not shown:
            state[key] = "em espera enquanto você usa o app (modo leve)"
            shown = True
        time.sleep(step_s)


def checkpoint(db) -> None:
    """Enxuga o arquivo de escrita do SQLite (WAL) quando a tela está parada."""
    if ui_active(30):
        return
    try:
        with db.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except Exception:
        pass
