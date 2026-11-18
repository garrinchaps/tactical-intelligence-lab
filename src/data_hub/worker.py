"""
Processo de fundo do Tactical Intelligence Lab (rodada 7 — velocidade).

Antes, a FotMob, a conversão do OpenPlay, a sincronização diária e o ao vivo rodavam como THREADS dentro do
processo do Streamlit. Contas pesadas em pandas disputavam o mesmo interpretador da tela (GIL), e cada jogo
gravado invalidava a versão do catálogo na memória da tela, que relia 300 mil partidas no clique seguinte.

Agora tudo isso roda AQUI, num processo separado e com prioridade baixa:
  * a tela não perde velocidade (outro processo, outro interpretador);
  * gravações daqui não mexem no cache da tela (ela adota a versão nova no ritmo de `stable_version`, 10 min);
  * o andamento vai para `data/worker_status.json`, que a tela só lê;
  * o processo encerra sozinho quando o app (processo pai) fecha — nada fica rodando escondido.

Uso manual (opcional): python -m src.data_hub.worker  (sem --pai, roda até Ctrl+C)
Desligar o processo e voltar às threads antigas: AUTO_SYNC_MODE=thread no .env.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

STATUS_PATH = Path("data/worker_status.json")
PID_PATH = Path("data/worker.pid")
HEARTBEAT_S = 5


def pid_alive(pid: int) -> bool:
    """Processo ainda existe? (no Windows, os.kill(pid, 0) MATA o processo — por isso a API do Windows)."""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _jsonable(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, (str, int, float, bool, type(None), list)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def write_status(extra: Optional[Dict[str, Any]] = None) -> None:
    from src.data_hub import autosync as A

    data = {"pid": os.getpid(), "heartbeat": datetime.now(timezone.utc).isoformat(),
            "sync": _jsonable(A._state), "fotmob": _jsonable(A._fm), "openplay": _jsonable(A._OPENPLAY),
            "live": _jsonable(A._live), **(extra or {})}
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATUS_PATH)


def read_status(max_age_s: float = 60) -> Optional[Dict[str, Any]]:
    """Andamento do processo de fundo; None se ele não está vivo (sem batimento recente)."""
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        hb = datetime.fromisoformat(data["heartbeat"])
        if (datetime.now(timezone.utc) - hb).total_seconds() > max_age_s:
            return None
        return data
    except Exception:
        return None


def _lower_priority() -> None:
    try:
        if os.name == "nt":
            import ctypes

            BELOW_NORMAL = 0x4000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), BELOW_NORMAL)
        else:
            os.nice(10)
    except Exception:
        pass


def _scheduled_sync_loop(db) -> None:
    """A sincronização de 3 h / 24 h (antes disparada pela tela) agora roda aqui, conferindo a cada 10 min."""
    from src.data_hub import autosync as A

    while A.enabled():
        try:
            if not A._state["running"]:
                pending = A.due(db)
                if pending:
                    A._state.update(running=True, last_attempt=datetime.now(timezone.utc), due=pending)
                    A._run(pending, db)
        except Exception as exc:
            A._state["last_error"] = f"{type(exc).__name__}: {exc}"
        try:
            nxt = A._next(db)
            A._state["next_quick"] = nxt.isoformat() if nxt else None
        except Exception:
            pass
        time.sleep(600)


_scout_state: Dict[str, Any] = {"ultima": None, "erro": None, "rodando": False}


def _scout_snapshot_loop(db) -> None:
    """Refaz a fotografia do universo do Scout quando ela passa de SCOUT_SNAPSHOT_HOURS (confere a cada 15 min)."""
    from src.scout import snapshot as S

    time.sleep(60)                                   # deixa o app abrir primeiro
    while True:
        try:
            a = S.age_hours()
            if a is None or a >= S.max_age_hours():
                _scout_state["rodando"] = True
                m = S.rebuild(db)
                _scout_state.update(ultima=m.get("built_at"), erro=None)
        except Exception as exc:
            _scout_state["erro"] = f"{type(exc).__name__}: {exc}"
        finally:
            _scout_state["rodando"] = False
        time.sleep(900)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Processo de fundo: FotMob, OpenPlay, sincronização e ao vivo.")
    ap.add_argument("--pai", type=int, default=0, help="PID do app; o processo encerra quando o app fecha")
    a = ap.parse_args(argv)
    os.environ["TIL_IN_WORKER"] = "1"
    _lower_priority()
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    from src.data_hub import autosync as A
    from src.data_hub.db import DataHubDB

    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    db = DataHubDB()
    A.start_threads(db)
    threading.Thread(target=_scheduled_sync_loop, args=(db,), daemon=True, name="til-autosync").start()
    threading.Thread(target=_scout_snapshot_loop, args=(db,), daemon=True, name="til-scout").start()
    try:
        while True:
            write_status({"scout": _jsonable(_scout_state)})
            if a.pai and not pid_alive(a.pai):
                break                                    # o app fechou: encerra junto
            time.sleep(HEARTBEAT_S)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if PID_PATH.exists() and PID_PATH.read_text().strip() == str(os.getpid()):
                PID_PATH.unlink()
        except Exception:
            pass
    return 0


_spawn_lock = threading.Lock()


def ensure_worker() -> bool:
    """Chamado pela TELA: garante um (só um) processo de fundo vivo. Barato — lê um arquivo."""
    if read_status(max_age_s=30):
        return True
    with _spawn_lock:
        try:
            pid = int(PID_PATH.read_text().strip()) if PID_PATH.exists() else 0
        except Exception:
            pid = 0
        if pid and pid_alive(pid):
            return True                                  # já subindo (ainda sem batimento)
        import subprocess

        flags = 0
        kw: Dict[str, Any] = {}
        if os.name == "nt":
            flags = 0x08000000 | 0x00004000             # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS
            kw["creationflags"] = flags
        else:
            kw["start_new_session"] = True
        log = Path("data/worker.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        fh = open(log, "a", encoding="utf-8")
        p = subprocess.Popen([sys.executable, "-m", "src.data_hub.worker", "--pai", str(os.getpid())],
                             cwd=str(Path.cwd()), stdout=fh, stderr=fh, stdin=subprocess.DEVNULL, **kw)
        PID_PATH.write_text(str(p.pid), encoding="utf-8")
        return True


if __name__ == "__main__":
    sys.exit(main())
