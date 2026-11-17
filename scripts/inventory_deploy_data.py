"""Inventário não destrutivo da base local antes de uma migração para hospedagem.

Não copia, altera, compacta ou remove dados. Produz apenas um JSON com integridade,
contagem de registros e tamanhos para dimensionar e validar a migração.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def directory_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "files": 0, "bytes": 0}
    count = total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
                count += 1
            except OSError:
                continue
    return {"exists": True, "files": count, "bytes": total}


def database_stats(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "integrity_check": None,
        "tables": {},
        "table_count": 0,
        "total_rows": 0,
        "sidecars": {},
    }
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        result["sidecars"][suffix] = sidecar.stat().st_size if sidecar.exists() else 0
    if not path.is_file():
        return result

    # URI read-only: não cria um banco vazio nem altera o banco de origem.
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        result["integrity_check"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        counts: dict[str, int | str] = {}
        for (name,) in tables:
            quoted = '"' + str(name).replace('"', '""') + '"'
            try:
                counts[str(name)] = int(conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
            except sqlite3.Error as exc:
                counts[str(name)] = f"ERRO: {exc}"
        result["tables"] = counts
        result["table_count"] = len(counts)
        result["total_rows"] = sum(v for v in counts.values() if isinstance(v, int))
    finally:
        conn.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="public_deploy_inventory.json",
                        help="Arquivo JSON de saída (padrão: public_deploy_inventory.json)")
    parser.add_argument("--database", default=os.getenv("DATABASE_PATH", "database/tactical_lab.db"),
                        help="Caminho do SQLite; por padrão usa DATABASE_PATH ou database/tactical_lab.db")
    args = parser.parse_args()

    db_path = Path(args.database)
    if not db_path.is_absolute():
        db_path = ROOT / db_path

    inventory = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(ROOT),
        "database": database_stats(db_path),
        "directories": {
            rel: directory_stats(ROOT / rel)
            for rel in ("data/raw", "data/lake", "data/processed", "data/demo", "models", "config")
        },
        "notes": [
            "Leitura somente; nenhum dado foi alterado.",
            "O SQLite foi aberto em modo read-only; arquivos WAL/SHM são contabilizados separadamente.",
            "Este inventário não contém chaves de API nem o conteúdo das tabelas.",
        ],
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "database_exists": inventory["database"]["exists"],
        "integrity_check": inventory["database"]["integrity_check"],
        "tables": inventory["database"]["table_count"],
        "rows": inventory["database"]["total_rows"],
        "database_bytes": inventory["database"]["bytes"],
        "directories": inventory["directories"],
    }, ensure_ascii=False, indent=2))
    return 0 if inventory["database"]["exists"] and inventory["database"]["integrity_check"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
