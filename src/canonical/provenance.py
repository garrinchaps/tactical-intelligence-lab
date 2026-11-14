"""
ProvenanceRegistry (Bloco 2).

Toda métrica exibida na interface é registrada com sua origem: fonte, conector, licença,
tier de confiança, momento da ingestão e o MÉTODO de cálculo (de onde o número sai).
Os componentes visuais exigem um registro; em modo estrito (TIL_STRICT_PROVENANCE=1,
usado nos testes) uma métrica sem proveniência gera MissingProvenanceError.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.canonical.schema import CONFIDENCE_TIERS, utc_now_iso


class MissingProvenanceError(RuntimeError):
    """Uma métrica tentou ser exibida sem registro de origem."""


def strict_mode() -> bool:
    return os.getenv("TIL_STRICT_PROVENANCE", "0") == "1"


@dataclass
class ProvenanceRecord:
    key: str
    label: str
    value: Any
    source: str
    connector: str
    license: str
    confidence_tier: str
    method: str
    match_id: Optional[str] = None
    ingestion_timestamp: str = field(default_factory=utc_now_iso)
    generator: Optional[str] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    inputs: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.confidence_tier not in CONFIDENCE_TIERS:
            raise ValueError(f"tier inválido: {self.confidence_tier}")
        for name in ("source", "connector", "license", "method"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"proveniência sem '{name}' para a métrica '{self.key}'")

    @property
    def is_simulated(self) -> bool:
        return self.confidence_tier == "SIMULATED"

    def simulated_label(self) -> str:
        """Selo obrigatório de toda métrica simulada (formulação fixa da seção 10)."""
        ci = ""
        if self.ci_low is not None and self.ci_high is not None:
            ci = (f" · IC 95% [{self.ci_low:g}; {self.ci_high:g}] — IC 95% da reamostragem, "
                  "condicionado à distribuição empírica de referência")
        return f"⚠️ DADOS SIMULADOS / MODELAGEM PROBABILÍSTICA · gerador: {self.generator or 'não informado'}{ci}"

    def short(self) -> str:
        return f"{self.source} · {self.confidence_tier} · {self.method}"


class ProvenanceRegistry:
    """Registro em memória (por renderização/sessão) com persistência opcional em SQLite."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self._records: Dict[str, ProvenanceRecord] = {}
        self.db_path = Path(db_path) if db_path else None

    def register(self, record: ProvenanceRecord) -> ProvenanceRecord:
        self._records[record.key] = record
        return record

    def get(self, key: str) -> Optional[ProvenanceRecord]:
        return self._records.get(key)

    def require(self, key: str) -> ProvenanceRecord:
        rec = self.get(key)
        if rec is None:
            raise MissingProvenanceError(f"métrica '{key}' sem proveniência registrada")
        return rec

    def records(self) -> List[ProvenanceRecord]:
        return list(self._records.values())

    def clear(self) -> None:
        self._records.clear()

    def as_rows(self) -> List[Dict[str, Any]]:
        rows = []
        for r in self._records.values():
            d = asdict(r)
            d["value"] = r.value if isinstance(r.value, (int, float, str)) else str(r.value)
            d["inputs"] = ", ".join(r.inputs)
            rows.append(d)
        return rows

    def persist(self) -> int:
        """Grava os registros atuais na tabela provenance_log (auditoria posterior)."""
        if not self.db_path:
            return 0
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS provenance_log (
                       id INTEGER PRIMARY KEY AUTOINCREMENT, metric_key TEXT, label TEXT, value TEXT,
                       source TEXT, connector TEXT, license TEXT, confidence_tier TEXT, method TEXT,
                       match_id TEXT, ingestion_timestamp TEXT, generator TEXT, ci_low REAL, ci_high REAL,
                       inputs TEXT, logged_at TEXT)""")
            for r in self._records.values():
                conn.execute(
                    """INSERT INTO provenance_log (metric_key, label, value, source, connector, license,
                       confidence_tier, method, match_id, ingestion_timestamp, generator, ci_low, ci_high,
                       inputs, logged_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r.key, r.label, json.dumps(r.value, default=str), r.source, r.connector, r.license,
                     r.confidence_tier, r.method, r.match_id, r.ingestion_timestamp, r.generator, r.ci_low,
                     r.ci_high, ", ".join(r.inputs), utc_now_iso()))
        return len(self._records)
