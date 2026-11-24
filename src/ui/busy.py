"""
Rodada 27f — os trabalhos de SEGUNDO PLANO da própria tela (pré-aquecimento de jogos/times, times da busca) davam
lugar ao clique do usuário só quando terminavam: disputavam o processador com a página que você acabou de pedir.
Agora a página em montagem é marcada aqui e esses trabalhos esperam entre um passo e outro.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

_LOCK = threading.Lock()
_ACTIVE = {"n": 0, "last": 0.0}


@contextmanager
def foreground():
    """Envolve a montagem de uma página (app.py)."""
    with _LOCK:
        _ACTIVE["n"] += 1
        _ACTIVE["last"] = time.time()
    try:
        yield
    finally:
        with _LOCK:
            _ACTIVE["n"] = max(0, _ACTIVE["n"] - 1)
            _ACTIVE["last"] = time.time()


def user_busy(grace_s: float = 1.5) -> bool:
    return _ACTIVE["n"] > 0 or time.time() - _ACTIVE["last"] < grace_s


def yield_to_user(max_wait_s: float = 300, step_s: float = .25) -> None:
    """Chamado por trabalhos de fundo entre passos: espera a página do usuário terminar."""
    t0 = time.time()
    while user_busy() and time.time() - t0 < max_wait_s:
        time.sleep(step_s)
