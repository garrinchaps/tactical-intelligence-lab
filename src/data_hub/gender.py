"""Separa competições femininas e masculinas (o catálogo mistura as duas)."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

FEMALE_RX = re.compile(r"women|womens|woman|femin|frauen|female|\bwsl\b|nwsl|liga f\b|\bw-league|damallsvenskan|"
                       r"\bwfc\b|\blfc\b women| fem\b|\(w\)|division 1 f[eé]minine|brasileir[aã]o (a1 )?feminino", re.I)
MALE, FEMALE = "masculino", "feminino"
LABELS = {MALE: "♂ Masculino", FEMALE: "♀ Feminino", "todos": "Todos"}


def gender_of(row: Mapping[str, Any]) -> str:
    """Usa o gênero informado pela fonte (StatsBomb) e, sem ele, o nome da competição e das equipes."""
    extra = row.get("extra_json")
    if isinstance(extra, str) and extra:
        try:
            g = (json.loads(extra) or {}).get("gender")
            if g in ("female", "feminino"):
                return FEMALE
            if g in ("male", "masculino"):
                return MALE
        except (ValueError, TypeError):
            pass
    text = " ".join(str(row.get(k) or "") for k in ("competition_name", "home_team_name", "away_team_name"))
    return FEMALE if FEMALE_RX.search(text) else MALE
