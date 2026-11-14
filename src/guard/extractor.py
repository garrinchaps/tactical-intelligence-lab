"""Módulo 7.1 — NumericExtractor: números do texto com normalização BR/US."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# número com separadores: 1.234,56 | 1,234.56 | 12,5 | 0.83 | 977
_NUM = re.compile(r"(?<![\w.,/])[-−]?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?(?![\w])|(?<![\w.,/])[-−]?\d+(?:[.,]\d+)?(?![\w])")


@dataclass
class NumericMention:
    raw: str
    candidates: List[float]          # interpretações possíveis (ambiguidade BR/US)
    decimals: int                    # casas decimais exibidas (para tolerância de arredondamento)
    start: int
    end: int
    unit: str = ""                   # "%", "pp", "m", "min", "" ...
    context: str = ""

    @property
    def value(self) -> float:
        return self.candidates[0]

    @property
    def is_integer(self) -> bool:
        return self.decimals == 0 and float(self.value).is_integer()


def normalize(raw: str) -> List[float]:
    """Interpretações numéricas de um token. '1.234,56' → [1234.56]; '1.234' → [1234.0, 1.234]."""
    s = raw.replace("−", "-").strip()
    neg = s.startswith("-")
    s = s.lstrip("-")
    out: List[float] = []
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):   # BR: 1.234,56
            out = [float(s.replace(".", "").replace(",", "."))]
        else:                              # US: 1,234.56
            out = [float(s.replace(",", ""))]
    elif "," in s:
        head, tail = s.rsplit(",", 1)
        if len(tail) == 3 and s.count(",") >= 1 and head.replace(",", "").isdigit() and len(head) <= 3:
            out = [float(s.replace(",", "")), float(s.replace(",", "."))]   # ambíguo: 1,234
        elif s.count(",") > 1:
            out = [float(s.replace(",", ""))]
        else:
            out = [float(s.replace(",", "."))]                               # BR decimal: 12,5
    elif "." in s:
        head, tail = s.rsplit(".", 1)
        if len(tail) == 3 and len(head) <= 3 and s.count(".") == 1:
            out = [float(s), float(s.replace(".", ""))]                     # ambíguo: 1.234
        elif s.count(".") > 1:
            out = [float(s.replace(".", ""))]
        else:
            out = [float(s)]
    else:
        out = [float(s)]
    return [-v if neg else v for v in out]


def _decimals(raw: str, value: float) -> int:
    s = raw.replace("−", "-")
    for sep in (",", "."):
        if sep in s:
            tail = s.rsplit(sep, 1)[1]
            if not (len(tail) == 3 and float(value).is_integer()):
                return len(tail)
    return 0


class NumericExtractor:
    UNIT_RX = re.compile(r"^\s*(pp|p\.p\.|%|m\b|metros|min\b|minutos?|'|’|xg|xt)", re.IGNORECASE)

    @classmethod
    def extract(cls, text: str) -> List[NumericMention]:
        mentions: List[NumericMention] = []
        for m in _NUM.finditer(text or ""):
            raw = m.group(0)
            cands = normalize(raw)
            after = text[m.end(): m.end() + 12]
            um = cls.UNIT_RX.match(after)
            unit = um.group(1).lower() if um else ""
            mentions.append(NumericMention(raw=raw, candidates=cands, decimals=_decimals(raw, cands[0]),
                                           start=m.start(), end=m.end(), unit=unit,
                                           context=text[max(0, m.start() - 40): m.end() + 40]))
        return mentions
