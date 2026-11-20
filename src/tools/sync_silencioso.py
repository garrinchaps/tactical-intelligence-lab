"""
Rodada 22 — atualização da base pelo Agendador de Tarefas do Windows SEM janela.

A versão antiga do agendamento rodava `cmd /c ... python -m src.data_hub.sync` a cada 3 h: o Windows abria uma janela
preta de "cmd" (System32) toda vez — era a janela que aparecia sozinha. Agora a tarefa chama `pythonw.exe` (Python sem
console) com este módulo, que:
  * grava tudo em data/sync_log.txt (pythonw não tem onde imprimir);
  * NÃO roda se o app estiver aberto — o processo de fundo do app já atualiza (e o SQLite aceita um gravador por vez);
  * não roda duas vezes ao mesmo tempo (trava em data/sync_silencioso.lock).

    pythonw -m src.tools.sync_silencioso --rapido          # o que o agendamento de 3 h chama
    pythonw -m src.tools.sync_silencioso --diario          # o de 6 h da manhã
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

LOG = Path("data/sync_log.txt")
LOCK = Path("data/sync_silencioso.lock")


def _locked() -> bool:
    try:
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 6 * 3600:
            return True
    except OSError:
        pass
    return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        sys.stdout = sys.stderr = fh                    # pythonw: sem console; tudo vai para o arquivo
        stamp = time.strftime("%Y-%m-%d %H:%M")
        try:
            from src.data_hub import activity

            if activity.ui_active(120):
                print(f"[{stamp}] app aberto: o processo de fundo do app já atualiza — agendamento pulado.")
                return 0
        except Exception:
            pass
        if _locked():
            print(f"[{stamp}] outra atualização agendada ainda está rodando — pulado.")
            return 0
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
        try:
            from src.data_hub import sync

            args = ["--rapido"] if "--rapido" in argv or not argv else ["--days", "3", "--seasons", "0"]
            print(f"[{stamp}] atualização agendada: {' '.join(args)}")
            sys.argv = ["src.data_hub.sync", *args]
            sync.main()
            print(f"[{time.strftime('%Y-%m-%d %H:%M')}] concluída.")
        except SystemExit:
            pass
        except Exception as exc:
            print(f"[{time.strftime('%Y-%m-%d %H:%M')}] erro: {type(exc).__name__}: {exc}")
            return 1
        finally:
            try:
                LOCK.unlink()
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
