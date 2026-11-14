"""
Catálogo configurável de competições e times (parte do Módulo 3.2).

Fonte da verdade: arquivos YAML em config/ — o usuário estende o catálogo sem alterar
código criando config/competitions.local.yaml (lido depois do arquivo base; entradas com
o mesmo 'id' sobrescrevem). O catálogo é validado, espelhado no SQLite (tabela
competition_catalog) e consultado pela página Catálogo de Dados.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

try:  # PyYAML é opcional: sem ele (ex.: Python sem pacote pronto), usa o leitor embutido
    import yaml as _yaml

    _load_yaml, _YAMLError = _yaml.safe_load, _yaml.YAMLError
except ImportError:  # pragma: no cover - depende do ambiente
    from src.connectors.mini_yaml import MiniYAMLError as _YAMLError
    from src.connectors.mini_yaml import safe_load as _load_yaml

BASE_FILE = Path("config/competitions.yaml")
LOCAL_FILE = Path("config/competitions.local.yaml")
VALID_SOURCES = {"statsbomb", "wyscout", "api_football", "football_data", "espn", "arquivo_usuario", "simulado"}
VALID_LEVELS = {"EVENTS", "BOXSCORE", "RESULT", "SIMULATED"}
REQUIRED = ("id", "nome", "temporada", "fonte", "nivel_dado", "licenca")


class CatalogError(ValueError):
    """Entrada de catálogo inválida; a mensagem cita arquivo, entrada e campo."""


class CompetitionCatalog:
    def __init__(self, entries: List[Dict[str, Any]], files: List[str]):
        self.entries = entries
        self.files = files

    # ------------------------------------------------------------ carga
    @staticmethod
    def _validate_entry(e: Dict[str, Any], where: str) -> Dict[str, Any]:
        if not isinstance(e, dict):
            raise CatalogError(f"{where}: cada competição deve ser um mapa chave: valor.")
        for f in REQUIRED:
            if e.get(f) in (None, ""):
                raise CatalogError(f"{where} (id={e.get('id', '?')}): campo obrigatório '{f}' ausente.")
        if e["fonte"] not in VALID_SOURCES:
            raise CatalogError(f"{where} (id={e['id']}): campo 'fonte' = '{e['fonte']}' inválido; "
                               f"use um de {sorted(VALID_SOURCES)}.")
        if e["nivel_dado"] not in VALID_LEVELS:
            raise CatalogError(f"{where} (id={e['id']}): campo 'nivel_dado' = '{e['nivel_dado']}' inválido; "
                               f"use um de {sorted(VALID_LEVELS)}.")
        times = e.get("times") or []
        if not isinstance(times, list):
            raise CatalogError(f"{where} (id={e['id']}): campo 'times' deve ser uma lista.")
        out = dict(e)
        out["temporada"] = str(e["temporada"])
        out["times"] = [str(t) for t in times]
        return out

    @classmethod
    def load(cls, files: Optional[Iterable[Path]] = None) -> "CompetitionCatalog":
        paths = [Path(p) for p in (files or [BASE_FILE, LOCAL_FILE])]
        merged: Dict[str, Dict[str, Any]] = {}
        used: List[str] = []
        for path in paths:
            if not path.exists():
                continue
            try:
                doc = _load_yaml(path.read_text(encoding="utf-8")) or {}
            except _YAMLError as exc:
                raise CatalogError(f"{path}: YAML inválido ({exc}).")
            items = doc.get("competicoes")
            if not isinstance(items, list):
                raise CatalogError(f"{path}: chave raiz 'competicoes' ausente ou não é uma lista.")
            for i, e in enumerate(items):
                entry = cls._validate_entry(e, f"{path}, entrada {i + 1}")
                entry["arquivo"] = str(path)
                merged[entry["id"]] = entry
            used.append(str(path))
        return cls(list(merged.values()), used)

    # ---------------------------------------------------------- consulta
    def to_frame(self) -> pd.DataFrame:
        if not self.entries:
            return pd.DataFrame(columns=["id", "nome", "temporada", "fonte", "nivel_dado", "licenca", "n_times"])
        df = pd.DataFrame(self.entries)
        df["n_times"] = df["times"].apply(len)
        return df

    def query(self, text: str = "", fonte: Optional[str] = None, nivel: Optional[str] = None) -> pd.DataFrame:
        df = self.to_frame()
        if df.empty:
            return df
        if fonte:
            df = df[df["fonte"] == fonte]
        if nivel:
            df = df[df["nivel_dado"] == nivel]
        if text.strip():
            t = text.strip().lower()
            mask = df["nome"].str.lower().str.contains(t, regex=False) | df["temporada"].str.lower().str.contains(t, regex=False) | \
                df["times"].apply(lambda ts: any(t in x.lower() for x in ts))
            df = df[mask]
        return df

    def teams(self) -> List[str]:
        return sorted({t for e in self.entries for t in e["times"]})

    def sync_to_sqlite(self, db_path: Path | str = "database/tactical_lab.db") -> int:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS competition_catalog (
                id TEXT PRIMARY KEY, nome TEXT, temporada TEXT, fonte TEXT, nivel_dado TEXT,
                licenca TEXT, times TEXT, partidas INTEGER, arquivo TEXT)""")
            conn.execute("DELETE FROM competition_catalog")
            for e in self.entries:
                conn.execute("INSERT INTO competition_catalog VALUES (?,?,?,?,?,?,?,?,?)",
                             (e["id"], e["nome"], e["temporada"], e["fonte"], e["nivel_dado"], e["licenca"],
                              "|".join(e["times"]), e.get("partidas"), e.get("arquivo")))
        return len(self.entries)
