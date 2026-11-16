"""
Treino da rede neural em PROCESSO SEPARADO (v36): a tela Bastidores só dispara e acompanha. Antes o treino rodava
dentro da página do Streamlit; qualquer clique/recarga interrompia o treino e a tela travava por minutos.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE = Path("data/treino_estado.json")
LOG = Path("data/treino_log.txt")
PID = Path("data/treino.pid")


def _alive(pid: int) -> bool:
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=5).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def running() -> bool:
    try:
        return _alive(int(PID.read_text().strip()))
    except Exception:
        return False


def start(args: List[str]) -> bool:
    """Dispara `python -m src.machine_learning.model_registry --treinar <args>`; False se já houver treino rodando."""
    if running():
        return False
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"status": "rodando", "etapa": "iniciando…", "log": [], "resultados": []}), encoding="utf-8")
    cmd = [sys.executable, "-m", "src.machine_learning.model_registry", "--treinar", "--estado", str(STATE), *args]
    flags = {}
    if os.name == "nt":
        flags["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    with LOG.open("w", encoding="utf-8") as log:
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=os.getcwd(), **flags)
    PID.write_text(str(p.pid))
    return True


def stop() -> bool:
    try:
        pid = int(PID.read_text().strip())
    except Exception:
        return False
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            os.kill(pid, 15)
    except Exception:
        return False
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
        st["status"] = "interrompido"
        STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return True


def state() -> Optional[Dict[str, Any]]:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if st.get("status") == "rodando" and not running():
        st["status"] = "erro"                      # o processo morreu sem escrever o fim
        try:
            st["log"] = (st.get("log") or []) + LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]
        except Exception:
            pass
    return st
