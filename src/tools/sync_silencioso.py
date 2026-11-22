"""
Rodada 22 — atualização da base pelo Agendador de Tarefas do Windows SEM janela.

A versão antiga do agendamento rodava `cmd /c ... python -m src.data_hub.sync` a cada 3 h: o Windows abria uma janela
preta de "cmd" (System32) toda vez — era a janela que aparecia sozinha. Agora a tarefa chama `pythonw.exe` (Python sem
console) com este módulo, que:
  * grava tudo em data/sync_log.txt (pythonw não tem onde imprimir);
  * NÃO roda se o app estiver aberto — o processo de fundo do app já atualiza (e o SQLite aceita um gravador por vez);
  * não roda duas vezes ao mesmo tempo (trava em data/sync_silencioso.lock).

    pythonw -m src.tools.sync_silencioso --rapido          # o que o agendamento de 3 h chama
    pythonw -m src.tools.sync_silencioso --diario          # o de 6 h da manhã (acorda o PC se estiver em suspensão)
    pythonw -m src.tools.sync_silencioso --ao-ligar        # 2 min depois de entrar no Windows: recupera os dias perdidos
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

LOG = Path("data/sync_log.txt")
LOCK = Path("data/sync_silencioso.lock")


MANUAL = Path("data/atualizacao_manual.lock")      # rodada 25c: o atualizar_tudo.ps1 está rodando


def _locked() -> bool:
    try:
        for p in (LOCK, MANUAL):
            if p.exists() and time.time() - p.stat().st_mtime < 6 * 3600:
                return True
    except OSError:
        pass
    return False


def catch_up(detail_limit: int = 400) -> dict:
    """Resultados de cada dia perdido (FotMob, 1 pedido por dia, até 30 dias) e os detalhes desses jogos (estatísticas,
    escalações, números por jogador) — o que acontece "enquanto o PC estava desligado" entra assim que ele liga."""
    from datetime import timedelta

    from src.data_hub import autosync as A
    from src.data_hub.service import MatchDataService

    svc = MatchDataService()
    days = A.missing_days(svc.db)
    r = A.refresh_recent_results(svc.db)
    det = {}
    if A.fotmob_enabled() and days:
        det = svc.fotmob.fetch_details(None, since=(days[0] - timedelta(days=1)).isoformat(), limit=detail_limit)
    return {"dias": len(days), "resultados": r.get("fotmob", 0) + r.get("espn", 0), "detalhes": det.get("detalhes", 0)}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--esperar" in argv:                   # rodada 24: atalho da pasta Inicializar espera o Windows assentar
        try:
            time.sleep(min(600, int(argv[argv.index("--esperar") + 1])))
        except (ValueError, IndexError):
            time.sleep(120)
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
        try:                                   # rodada 23: recupera os dias em que o PC ficou desligado
            r = catch_up()
            print(f"[{stamp}] recuperação: {r}")
        except Exception as exc:
            print(f"[{stamp}] recuperação falhou: {type(exc).__name__}: {exc}")
        try:
            from src.data_hub import sync

            args = ["--rapido"] if "--rapido" in argv or "--ao-ligar" in argv or not argv else ["--days", "3", "--seasons", "0"]
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
