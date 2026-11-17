"""Manifests versionados para artefatos publicados pelo Data Hub.

O módulo é deliberadamente independente da interface e não altera o SQLite
legado. Ele descreve um arquivo já produzido pelo lake, permitindo validação
de checksum, proveniência, licença e schema antes da distribuição.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MANIFEST_VERSION = "1"


@dataclass(frozen=True)
class ArtifactManifest:
    artifact: str
    path: str
    format: str
    bytes: int
    sha256: str
    source: str
    connector: str
    license: str
    schema_version: str
    generated_at_utc: str
    columns: tuple[str, ...] = ()
    row_count: int | None = None
    redistributable: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["manifest_version"] = MANIFEST_VERSION
        payload["columns"] = list(self.columns)
        return payload


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format(path: Path) -> str:
    if path.name.endswith(".csv.gz"):
        return "csv.gz"
    return path.suffix.lstrip(".").lower() or "binary"


def build_manifest(
    path: Path | str,
    *,
    artifact: str | None = None,
    source: str,
    connector: str,
    license: str,
    schema_version: str = "1",
    columns: Iterable[str] = (),
    row_count: int | None = None,
    redistributable: bool = False,
) -> ArtifactManifest:
    """Cria um manifesto sem abrir, escrever ou migrar o banco de dados."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    return ArtifactManifest(
        artifact=artifact or file_path.stem.replace(".csv", ""),
        path=file_path.as_posix(),
        format=_format(file_path),
        bytes=file_path.stat().st_size,
        sha256=_sha256(file_path),
        source=source,
        connector=connector,
        license=license,
        schema_version=schema_version,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        columns=tuple(columns),
        row_count=row_count,
        redistributable=redistributable,
    )


def write_manifest(manifest: ArtifactManifest, destination: Path | str) -> Path:
    """Escreve JSON atômico; o diretório de destino é criado se necessário."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".partial")
    temporary.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target
