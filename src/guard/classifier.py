"""
Módulo 7.3 — Classifier: EXATO / DERIVADO / NÃO RASTREÁVEL.

EXATO           o número (em alguma interpretação BR/US) coincide com um fato do contexto,
                respeitando o arredondamento exibido (tolerância de meia unidade da última casa),
                ou é uma constante metodológica declarada (Zona 14, minuto 60...).
DERIVADO        recalculável por UMA operação entre dois fatos relacionados (irmãos no mesmo
                bloco do JSON, ou a mesma métrica de até 4 entidades), com operação compatível
                com a unidade escrita no texto:
                  "%"           → 100·parte/total entre contagens, ou proporção (0–1) convertida em %;
                  "pp"          → |a−b| (diferença entre duas taxas);
                  sem unidade   → a−b, |a−b|, a+b.
                Razões soltas (a/b sem unidade) não são aceitas: cobrem números demais.
NÃO RASTREÁVEL  nada acima explica o número.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import numpy as np

from src.guard.extractor import NumericMention
from src.guard.ground_truth import Fact, GroundTruthSet

EXATO, DERIVADO, NAO_RASTREAVEL, CONSTANTE = "EXATO", "DERIVADO", "NÃO RASTREÁVEL", "CONSTANTE"


@dataclass
class Classification:
    mention: NumericMention
    label: str
    explanation: str = ""

    @property
    def traceable(self) -> bool:
        return self.label != NAO_RASTREAVEL


class NumberClassifier:
    def __init__(self, gt: GroundTruthSet, constants: Optional[Set[float]] = None):
        self.gt = gt
        self.constants = constants or set()
        self._groups = self._related_groups(gt.facts)

    @staticmethod
    def _related_groups(facts: List[Fact]) -> List[np.ndarray]:
        by_parent: Dict[str, List[float]] = {}
        by_leaf: Dict[str, List[float]] = {}
        for f in facts:
            by_parent.setdefault(f.parent, []).append(f.value)
            by_leaf.setdefault(f.leaf, []).append(f.value)
        groups = [np.unique(np.array(v)) for v in by_parent.values() if 2 <= len(v) <= 80]
        groups += [np.unique(np.array(v)) for v in by_leaf.values() if 2 <= len(v) <= 4]
        return groups

    @staticmethod
    def _tol(m: NumericMention) -> float:
        return 0.5 * 10 ** (-m.decimals) + 1e-9

    def classify(self, m: NumericMention) -> Classification:
        tol = self._tol(m)
        vals = self.gt.values
        for c in m.candidates:
            if vals.size:
                hit = np.where(np.abs(vals - c) <= tol)[0]
                if hit.size:
                    return Classification(m, EXATO, f"= {self.gt.facts[int(hit[0])].path}")
        for c in m.candidates:
            if c in self.constants or abs(c) in self.constants:
                return Classification(m, CONSTANTE, "constante metodológica declarada")
        unit = m.unit
        if unit == "%":
            for c in m.candidates:
                frac = np.where((vals >= 0) & (vals <= 1))[0] if vals.size else np.array([], dtype=int)
                hit = frac[np.abs(vals[frac] * 100 - c) <= tol] if frac.size else frac
                if hit.size:
                    return Classification(m, DERIVADO, f"proporção→% de {self.gt.facts[int(hit[0])].path}")
        for c in m.candidates:
            for g in self._groups:
                a = g[:, None]
                b = g[None, :]
                with np.errstate(divide="ignore", invalid="ignore"):
                    if unit == "%":
                        # percentual derivado = parte ÷ total entre CONTAGENS (inteiros, 0 ≤ parte ≤ total)
                        counts = (a == np.round(a)) & (b == np.round(b)) & (a >= 0) & (a <= b) & (b > 0)
                        ops = {"100·parte/total": np.where(counts, 100 * a / np.where(b != 0, b, 1), np.nan)}
                    elif unit in ("pp", "p.p."):
                        ops = {"|a−b|": np.abs(a - b)}
                    else:
                        ops = {"a−b": a - b, "|a−b|": np.abs(a - b), "a+b": a + b}
                for name, res in ops.items():
                    mask = np.abs(res - c) <= tol
                    np.fill_diagonal(mask, False)
                    if mask.any():
                        i, j = np.argwhere(mask)[0]
                        return Classification(m, DERIVADO, f"{name} com a={g[i]:g}, b={g[j]:g}")
        return Classification(m, NAO_RASTREAVEL, "não encontrado nem recalculável a partir do contexto")
