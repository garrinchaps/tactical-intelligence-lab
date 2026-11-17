"""Bootstrap seguro do SQLite persistente usado pelo app.

O download remoto é usado somente quando ainda não existe um banco local utilizável.
Um banco pequeno que já contenha tabelas nunca é substituído silenciosamente.
Para substituição intencional, defina TACTICAL_ALLOW_DB_REPLACE=1; uma cópia consistente
é criada pelo SQLite Backup API antes do replace.
"""

from __future__ import annotations

import gzip
import gc
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB_PATH = Path("database/tactical_lab.db")
# Mantido por compatibilidade para ferramentas que importam esta constante.
DB_PATH = Path(
    os.getenv("TACTICAL_DB_PATH")
    or os.getenv("DATABASE_PATH")
    or str(DEFAULT_DB_PATH)
)
REPO_ID = os.getenv("HF_DATASET_REPO", "garrinchaps/tactical-intelligence-db")
HF_TOKEN = os.getenv("HF_TOKEN")
DB_REPLACE_ENV = "TACTICAL_ALLOW_DB_REPLACE"
LARGE_DB_BYTES = 10_000_000


def configured_db_path() -> Path:
    """Mesma precedência usada por DataHubDB, lida no momento da chamada."""
    return Path(
        os.getenv("TACTICAL_DB_PATH")
        or os.getenv("DATABASE_PATH")
        or str(DEFAULT_DB_PATH)
    )


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "sim", "on"}


def _user_tables(path: Path) -> list[str]:
    """Lista tabelas de usuário em modo somente leitura."""
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    try:
        conn.execute("PRAGMA query_only = ON")
        integrity = conn.execute("PRAGMA quick_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise sqlite3.DatabaseError(f"PRAGMA quick_check: {integrity[0] if integrity else 'sem resultado'}")
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
        del conn
        gc.collect()
    return [str(row[0]) for row in rows]


def _backup_existing_database(path: Path) -> Path:
    """Faz uma cópia consistente do banco, incluindo estado WAL, sem sobrescrever backups."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.pre-fetch-{stamp}.bak")
    source_uri = path.resolve().as_uri() + "?mode=ro"
    source = sqlite3.connect(source_uri, uri=True, timeout=30)
    destination = sqlite3.connect(str(backup_path), timeout=30)
    try:
        source.backup(destination)
        result = destination.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise sqlite3.DatabaseError(
                f"Backup SQLite não passou no quick_check: {result[0] if result else 'sem resultado'}"
            )
    except Exception:
        destination.close()
        source.close()
        if backup_path.exists():
            backup_path.unlink()
        raise
    else:
        destination.close()
        source.close()
        del destination, source
        gc.collect()
    return backup_path


def ensure_database(
    db_path: Path | str | None = None,
    *,
    token: str | None = None,
    repo_id: str | None = None,
) -> str:
    """Garante a existência do banco sem substituir dados locais sem autorização explícita."""
    target = Path(db_path) if db_path is not None else configured_db_path()
    selected_token = token if token is not None else os.getenv("HF_TOKEN")
    selected_repo = repo_id or os.getenv("HF_DATASET_REPO", "garrinchaps/tactical-intelligence-db")
    allow_replace = _truthy(os.getenv(DB_REPLACE_ENV))

    if target.exists():
        size = target.stat().st_size
        if size > 0:
            if size > LARGE_DB_BYTES and not allow_replace:
                print(f"Banco existente encontrado: {target}")
                return str(target)

            try:
                tables = _user_tables(target)
            except (OSError, sqlite3.Error) as exc:
                raise RuntimeError(
                    f"Banco existente em {target} não passou na verificação; "
                    "ele foi preservado e não será substituído automaticamente."
                ) from exc

            if tables and not allow_replace:
                raise RuntimeError(
                    f"Banco SQLite existente em {target} possui {len(tables)} tabela(s), "
                    "mas é menor que o limite de reconhecimento automático. "
                    f"Nenhum dado foi substituído. Faça backup e defina {DB_REPLACE_ENV}=1 "
                    "somente se a substituição remota for intencional."
                )

            if tables and allow_replace:
                backup_path = _backup_existing_database(target)
                print(f"Backup consistente do banco anterior: {backup_path}")

    if not selected_token:
        raise RuntimeError(
            "HF_TOKEN não configurado e o banco local ainda não está disponível. "
            "Configure HF_TOKEN ou forneça DATABASE_PATH/TACTICAL_DB_PATH."
        )

    from huggingface_hub import hf_hub_download

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Baixando banco de {selected_repo}...")

    gz_path = hf_hub_download(
        repo_id=selected_repo,
        filename="tactical_lab.db.gz",
        repo_type="dataset",
        token=selected_token,
    )

    temp_db = target.with_name(target.name + ".partial")
    try:
        print("Descompactando banco...")
        with gzip.open(gz_path, "rb") as source:
            with open(temp_db, "wb") as destination:
                shutil.copyfileobj(source, destination)

        print("Verificando integridade SQLite...")
        # O context manager controla a transação, mas não garante o
        # fechamento do handle em todas as versões do SQLite no Windows.
        # Fechar explicitamente antes do replace evita bloquear o .partial.
        conn = sqlite3.connect(str(temp_db))
        try:
            result = conn.execute("PRAGMA quick_check").fetchone()
        finally:
            conn.close()
            del conn
            gc.collect()
        if not result or result[0] != "ok":
            raise RuntimeError(
                f"Banco remoto inválido: {result[0] if result else 'sem resultado'}"
            )

        os.replace(temp_db, target)
        print(f"Banco pronto: {target}")
        return str(target)
    finally:
        if temp_db.exists():
            temp_db.unlink()


if __name__ == "__main__":
    ensure_database()
