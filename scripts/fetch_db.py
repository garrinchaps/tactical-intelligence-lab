import gzip
import os
import shutil
import sqlite3
from pathlib import Path


DB_PATH = Path(
    os.getenv("TACTICAL_DB_PATH")
    or os.getenv("DATABASE_PATH")
    or "database/tactical_lab.db"
)

REPO_ID = os.getenv(
    "HF_DATASET_REPO",
    "garrinchaps/tactical-intelligence-db"
)

HF_TOKEN = os.getenv("HF_TOKEN")


def ensure_database():
    if DB_PATH.exists() and DB_PATH.stat().st_size > 10_000_000:
        print(f"Banco existente encontrado: {DB_PATH}")
        return str(DB_PATH)

    if not HF_TOKEN:
        raise RuntimeError(
            "HF_TOKEN nao configurado. Configure o token de leitura."
        )
    from huggingface_hub import hf_hub_download

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Baixando banco de {REPO_ID}...")

    gz_path = hf_hub_download(
        repo_id=REPO_ID,
        filename="tactical_lab.db.gz",
        repo_type="dataset",
        token=HF_TOKEN,
    )

    temp_db = DB_PATH.with_name(DB_PATH.name + ".partial")

    try:
        print("Descompactando banco...")

        with gzip.open(gz_path, "rb") as source:
            with open(temp_db, "wb") as destination:
                shutil.copyfileobj(source, destination)

        print("Verificando integridade SQLite...")

        with sqlite3.connect(str(temp_db)) as conn:
            result = conn.execute("PRAGMA quick_check").fetchone()[0]

        if result != "ok":
            raise RuntimeError(f"Banco invalido: {result}")

        os.replace(temp_db, DB_PATH)

        print(f"Banco pronto: {DB_PATH}")
        return str(DB_PATH)

    finally:
        if temp_db.exists():
            temp_db.unlink()


if __name__ == "__main__":
    ensure_database()
