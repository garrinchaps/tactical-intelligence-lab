"""Exportação seletiva e somente leitura do SQLite para artefatos do Data Hub."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from src.data_hub.artifacts import ArtifactManifest, build_manifest, write_manifest

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ExportResult:
    artifact: Path
    manifest: Path
    rows: int
    checksum: str


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Identificador SQLite inválido: {value!r}")
    return value


def _read_only(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=30)


def export_table(
    db_path: Path | str,
    *,
    table: str,
    destination: Path | str,
    source: str,
    connector: str,
    license: str,
    columns: Sequence[str] | None = None,
    where: str | None = None,
    params: Sequence[Any] = (),
    chunk_size: int = 50_000,
    redistributable: bool = False,
) -> ExportResult:
    """Exporta uma seleção parametrizada, sem executar SQL arbitrário.

    O destino `.csv.gz` é sempre suportado e usa chunks. `.parquet` requer
    `pyarrow` instalado, pois o SQLite não deve ser carregado inteiro em RAM.
    """
    db = Path(db_path)
    target = Path(destination)
    if not db.is_file():
        raise FileNotFoundError(db)
    if chunk_size < 1:
        raise ValueError("chunk_size deve ser positivo")
    if where and any(token in where for token in (";", "--", "/*", "*/")):
        raise ValueError("where contém tokens SQL não permitidos")
    if target.suffix == ".parquet":
        try:
            import pyarrow  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("Exportação Parquet exige pyarrow instalado") from exc
    if target.name.endswith(".csv.gz"):
        output_format = "csv.gz"
    elif target.suffix == ".parquet":
        output_format = "parquet"
    else:
        raise ValueError("O destino deve terminar em .csv.gz ou .parquet")

    table_name = _identifier(table)
    selected = "*" if not columns else ", ".join(_identifier(c) for c in columns)
    predicate = f" WHERE {where}" if where else ""
    query = f'SELECT {selected} FROM "{table_name}"{predicate}'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".partial")
    rows = 0
    frames: list[pd.DataFrame] = []
    conn = _read_only(db)
    try:
        column_names = [item[0] for item in conn.execute(query, tuple(params)).description]
        for frame in pd.read_sql_query(query, conn, params=tuple(params), chunksize=chunk_size):
            rows += len(frame)
            if output_format == "parquet":
                frames.append(frame)
            else:
                frame.to_csv(
                    temporary,
                    mode="a" if rows > len(frame) else "w",
                    index=False,
                    header=rows == len(frame),
                    compression="gzip",
                )
    finally:
        conn.close()
    if output_format == "parquet":
        (pd.concat(frames, ignore_index=True)
         if frames else pd.DataFrame(columns=column_names)).to_parquet(temporary, index=False)
    temporary.replace(target)
    manifest_obj: ArtifactManifest = build_manifest(
        target,
        artifact=target.name.replace(".csv.gz", "").replace(".parquet", ""),
        source=source,
        connector=connector,
        license=license,
        columns=tuple(column_names),
        row_count=rows,
        redistributable=redistributable,
    )
    manifest_path = target.with_suffix(target.suffix + ".manifest.json")
    write_manifest(manifest_obj, manifest_path)
    return ExportResult(target, manifest_path, rows, manifest_obj.sha256)
