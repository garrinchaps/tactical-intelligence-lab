"""Separa competições femininas e masculinas (o catálogo mistura as duas)."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

FEMALE_RX = re.compile(r"women|womens|woman|femin|frauen|female|\bwsl\b|nwsl|liga f\b|\bw-league|damallsvenskan|"
                       r"\bwfc\b|\blfc\b women| fem\b|\(w\)|division 1 f[eé]minine|brasileir[aã]o (?:a1 )?feminino", re.I)
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


def gender_series(df):
    """Versão vetorizada de gender_of para o catálogo inteiro (dezenas de milhares de linhas)."""
    import pandas as pd

    if df is None or df.empty:
        return pd.Series(dtype=str)
    ex = df["extra_json"].fillna("") if "extra_json" in df.columns else pd.Series("", index=df.index)
    female_src = ex.str.contains(r'"gender":\s*"(?:female|feminino)"', regex=True)
    male_src = ex.str.contains(r'"gender":\s*"(?:male|masculino)"', regex=True)
    text = (df.get("competition_name", "").fillna("").astype(str) + " " + df.get("home_team_name", "").fillna("").astype(str)
            + " " + df.get("away_team_name", "").fillna("").astype(str))
    by_name = text.str.contains(FEMALE_RX.pattern, flags=re.I, regex=True)
    out = pd.Series(MALE, index=df.index)
    out[(female_src) | (~male_src & by_name)] = FEMALE
    return out
