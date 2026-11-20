"""
Rodada 22 — no SERVIDOR (ex.: Streamlit Community Cloud), baixa a base núcleo na primeira abertura.

Ativa só quando existe `TIL_NUCLEO_URL` (variável de ambiente ou `st.secrets`) e o banco ainda não está no disco.
Se o arquivo for privado (recomendado — ver licenças no plano), `HF_TOKEN` vai como cabeçalho de autorização.
O token nunca é impresso nem registrado. No PC do usuário nada disso roda (a variável não existe lá).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional


def _secret(name: str) -> str:
    v = os.getenv(name, "")
    if v:
        return v
    try:
        import streamlit as st

        return str(st.secrets.get(name, "") or "")
    except Exception:
        return ""


def target_path() -> Path:
    from src.data_hub.db import DEFAULT_DB

    return Path(os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or DEFAULT_DB)


def ensure_database(progress=None) -> Optional[str]:
    """Baixa o núcleo se configurado e ausente. Devolve uma mensagem curta (ou None se não precisou)."""
    url = _secret("TIL_NUCLEO_URL")
    if not url:
        return None
    dest = target_path()
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return None
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".baixando")
    headers = {"User-Agent": "tactical-lab"}
    tok = _secret("HF_TOKEN")
    if tok:
        headers["Authorization"] = "Bearer " + tok
    t0, done = time.time(), 0
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=60) as r:
        if r.status_code != 200:
            return f"não consegui baixar a base núcleo (HTTP {r.status_code})"
        total = int(r.headers.get("content-length") or 0)
        with open(tmp, "wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    os.replace(tmp, dest)
    return f"base núcleo baixada ({done / 1e9:.2f} GB em {time.time() - t0:.0f} s)"


def first_run_gate() -> None:
    """Chamado no topo do app: mostra uma barra enquanto baixa (só na 1ª abertura do servidor)."""
    if not _secret("TIL_NUCLEO_URL") or (target_path().exists() and target_path().stat().st_size > 1_000_000):
        return
    import streamlit as st

    st.info("Preparando a base de dados do laboratório (só na primeira abertura do servidor)…")
    bar = st.progress(0.0)
    msg = ensure_database(progress=lambda f: bar.progress(min(1.0, f)))
    if msg:
        st.caption(msg)
