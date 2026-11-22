"""
Rodada 25c — espera o banco ficar livre para gravar (SÓ LEITURA até conseguir; não altera nada).

    python -m src.tools.esperar_banco            # espera até 5 min
    python -m src.tools.esperar_banco --max 600

Tenta abrir uma transação de escrita e desfazê-la na hora. Enquanto outro processo do laboratório estiver gravando,
avisa a cada 15 s. Sai com código 0 quando o banco está livre e 1 se o tempo acabar.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path


def db_path() -> Path:
    """Mesmo caminho que o app usa (variável TACTICAL_DB_PATH/DATABASE_PATH do ambiente ou o padrão)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()            # só carrega as variáveis no processo; nada é exibido
    except Exception:
        pass
    try:
        from src.data_hub.db import DEFAULT_DB  # type: ignore
    except Exception:
        DEFAULT_DB = "database/tactical_lab.db"
    return Path(os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or str(DEFAULT_DB))


def free(path: Path) -> bool:
    try:
        c = sqlite3.connect(str(path), timeout=2)
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute("ROLLBACK")
            return True
        finally:
            c.close()
    except sqlite3.OperationalError:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=300)
    a = ap.parse_args(argv)
    p = db_path()
    if not p.exists():
        print(f"Banco ainda não existe ({p}) — nada a esperar.")
        return 0
    t0 = time.time()
    last = 0.0
    while time.time() - t0 < a.max:
        if free(p):
            print("Banco livre para gravar.")
            return 0
        if time.time() - last >= 15:
            print(f"Banco ocupado por outro processo do laboratório… esperando ({time.time() - t0:.0f} s)", flush=True)
            last = time.time()
        time.sleep(3)
    print("O banco continuou ocupado. Feche o app, espere 1 minuto e rode o script de novo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
