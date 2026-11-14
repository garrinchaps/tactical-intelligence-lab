"""
Backup local de segurança (biblioteca padrão): copia data/ e os bancos SQLite para backups/<data-hora>/.

    python -m src.tools.backup_local            # faz o backup
    python -m src.tools.backup_local --listar   # mostra os backups existentes

O banco é copiado pela API de backup do SQLite (cópia consistente mesmo com o app aberto).
Para reverter: feche o app e copie de volta a pasta/arquivo do backup escolhido.
A pasta backups/ está no .gitignore e nunca vai para o Git.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"__pycache__"}


def backup(root: Path = ROOT, dest_root: Path | None = None) -> Path:
    dest = (dest_root or root / "backups") / datetime.now().strftime("%Y%m%d_%H%M%S")
    dest.mkdir(parents=True, exist_ok=False)
    data = root / "data"
    if data.exists():
        shutil.copytree(data, dest / "data", ignore=shutil.ignore_patterns(*SKIP_DIRS))
    dbs = sorted((root / "database").glob("*.db")) if (root / "database").exists() else []
    (dest / "database").mkdir(exist_ok=True)
    for db in dbs:
        src = sqlite3.connect(str(db))
        out = sqlite3.connect(str(dest / "database" / db.name))
        with out:
            src.backup(out)
        src.close()
        out.close()
    n_files = sum(1 for p in dest.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    (dest / "LEIA-ME.txt").write_text(
        f"Backup de {datetime.now():%d/%m/%Y %H:%M}\n{n_files} arquivos, {size / 1e6:.1f} MB\n"
        "Para reverter: feche o app; copie data/ e database/*.db desta pasta de volta para a raiz do projeto.\n",
        encoding="utf-8")
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true")
    a = ap.parse_args(argv)
    if a.listar:
        for p in sorted((ROOT / "backups").glob("*")):
            print(p.name)
        return 0
    d = backup()
    print(f"Backup criado em {d}")
    return 0


if __name__ == "__main__":
    try:  # lê o .env (OPENPLAY_PATH, CBF_SUMULAS_PATH, caminho do banco...) também quando rodado direto
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    sys.exit(main())
