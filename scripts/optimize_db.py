"""Cria índices analíticos pesados sob demanda, fora da inicialização interativa do app.

Uso: python scripts/optimize_db.py --database database/tactical_lab.db
A operação é aditiva: não apaga nem reescreve tabelas ou registros.
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Otimização aditiva do SQLite do Tactical Intelligence Lab.")
    parser.add_argument("--database", default="database/tactical_lab.db", help="Arquivo SQLite local.")
    args = parser.parse_args()
    path = Path(args.database).expanduser().resolve()
    if not path.is_file():
        parser.error(f"Banco não encontrado: {path}")
    print("Índice de cobertura do Scout — manutenção única", flush=True)
    print(f"Banco: {path}", flush=True)
    print(f"Tamanho: {path.stat().st_size / (1024 ** 3):.2f} GiB", flush=True)
    print("A operação não altera registros, mas pode levar alguns minutos e ocupar disco/CPU.", flush=True)
    started = time.perf_counter()
    conn = sqlite3.connect(str(path), timeout=300)
    try:
        conn.execute("PRAGMA busy_timeout = 300000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA cache_size = -262144")
        conn.execute("PRAGMA temp_store = FILE")
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"matches", "match_player_stats"}.issubset(tables):
            raise RuntimeError("O banco não contém as tabelas necessárias do Data Hub.")
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                              ("idx_pstats_match_player_minutes",)).fetchone()
        if exists:
            print("Índice já existe; nenhuma alteração necessária.", flush=True)
            return 0
        print("Criando índice (pode demorar em bases com milhões de atuações)...", flush=True)
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_pstats_match_player_minutes
                        ON match_player_stats(match_id, minutes, player_name)""")
        conn.commit()
        print(f"Índice criado em {time.perf_counter() - started:.1f}s.", flush=True)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
