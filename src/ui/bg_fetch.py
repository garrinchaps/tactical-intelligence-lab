"""
Rodada 27f — downloads feitos A PEDIDO DA TELA (FotMob: últimos jogos de um time, elenco atual; ESPN: escalação oficial e
notícias) rodavam DENTRO do clique: 12 jogos × pausa entre pedidos × tentativas = 1 a 5 minutos na Escalação.
Agora a tela mostra na hora o que já está na base e o download roda numa thread; quando termina, a versão do time muda
(jogos novos) e a próxima abertura já vem completa. Um download por chave a cada `cooldown_s`.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

_LOCK = threading.Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}


def schedule(key: str, fn: Callable[[], Any], cooldown_s: float = 1800) -> bool:
    """Roda `fn` em segundo plano (se não rodou com esta chave nos últimos `cooldown_s`). True = está baixando."""
    now = time.time()
    with _LOCK:
        job = _JOBS.get(key)
        if job and (job["running"] or now - job["t"] < cooldown_s):
            return bool(job["running"])
        job = _JOBS[key] = {"t": now, "running": True, "value": job.get("value") if job else None, "error": None}

    def run():
        try:
            from src.ui.busy import yield_to_user

            yield_to_user(max_wait_s=20)               # deixa a página que pediu terminar primeiro
            job["value"] = fn()
        except Exception as exc:                       # noqa: BLE001
            job["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            job["running"] = False
            job["t"] = time.time()

    threading.Thread(target=run, name=f"til-bg-{key[:30]}", daemon=True).start()
    return True


def value(key: str, fn: Callable[[], Any], ttl_s: float = 900) -> Optional[Any]:
    """Último resultado de `fn` (ou None enquanto baixa) — refeito em segundo plano a cada `ttl_s`."""
    job = _JOBS.get(key)
    schedule(key, fn, cooldown_s=ttl_s)
    return job.get("value") if job else None


def running(key: str) -> bool:
    job = _JOBS.get(key)
    return bool(job and job["running"])


def in_ui() -> bool:
    """Estamos dentro do app (Streamlit) — e não num script/CLI/teste, onde o download pode ser na hora."""
    try:
        from streamlit.runtime import exists

        return bool(exists())
    except Exception:
        return False


def running_for(text: str) -> bool:
    """Algum download em segundo plano citando este time/jogo está rodando?"""
    t = str(text or "")
    return bool(t) and any(j["running"] and t in k for k, j in list(_JOBS.items()))
