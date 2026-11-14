"""Módulo 7.2 — GroundTruthSet: conjunto fechado de métricas que compôs o contexto da geração."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Tuple

import numpy as np


@dataclass(frozen=True)
class Fact:
    path: str        # caminho no JSON (ex.: blocos.defesa_no_recorte.duelos_no_setor)
    value: float

    @property
    def parent(self) -> str:
        return self.path.rsplit(".", 1)[0] if "." in self.path else ""

    @property
    def leaf(self) -> str:
        return re.sub(r"\[\d+\]", "", self.path.rsplit(".", 1)[-1])


class GroundTruthSet:
    def __init__(self, facts: List[Fact]):
        self.facts = facts
        self.values = np.array([f.value for f in facts], dtype=float) if facts else np.zeros(0)

    @classmethod
    def from_evidence(cls, evidence: Any, skip_keys: Tuple[str, ...] = ("user_query",)) -> "GroundTruthSet":
        facts: List[Fact] = []

        def walk(obj: Any, path: str) -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in skip_keys:
                        continue
                    walk(v, f"{path}.{k}" if path else str(k))
            elif isinstance(obj, (list, tuple)):
                for i, v in enumerate(obj):
                    walk(v, f"{path}[{i}]")
            elif isinstance(obj, bool) or obj is None:
                return
            elif isinstance(obj, (int, float, np.integer, np.floating)):
                v = float(obj)
                if np.isfinite(v):
                    facts.append(Fact(path, v))
            elif isinstance(obj, str):
                # números citados em textos prontos das evidências (ex.: diagnósticos)
                for tok in re.findall(r"(?<![\w.])\d+(?:[.,]\d+)?", obj):
                    try:
                        facts.append(Fact(f"{path}#texto", float(tok.replace(",", "."))))
                    except ValueError:
                        pass

        walk(evidence, "")
        return cls(facts)

    def __len__(self) -> int:
        return len(self.facts)
