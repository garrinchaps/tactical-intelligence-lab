"""Separa competições femininas e masculinas (o catálogo mistura as duas)."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping, Sequence

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


# ----------------------------------------------------------------------------------------------- rodada 10
# As fontes dão o MESMO nome ao time masculino e ao feminino ("Bayern München" na Bundesliga e na Frauen-Bundesliga).
# Sem separar pela competição, a Escalação do Bayern misturava Harry Kane com Klara Bühl. Regra: o time é feminino se
# algum dos nomes dele traz marca de feminino; senão, só entram competições masculinas — e vice-versa.
# padrões (minúsculo) de competições femininas, como as fontes gravam
WOMEN_LIKE = ["%femin%", "%women%", "%frauen%", "%femmin%", "%femen%", "%feminil%", "liga f %", "liga f(%", "liga f",
              "%première ligue%", "%premiere ligue%", "%nwsl%", "%wsl%", "%damallsvenskan%", "%toppserien%",
              "%(w)%", "%w-league%", "%kvindeliga%", "%damen%"]
_WOMEN_RE = re.compile(r"femin|women|frauen|femmin|femen|feminil|^liga f\b|premi[eè]re ligue|nwsl|\bwsl\b|"
                       r"damallsvenskan|toppserien|\(w\)|w-league|kvindeliga|damen", re.I)
_TEAM_RE = re.compile(r"\b(women|woman|feminino|femenino|féminin|feminine|frauen|ladies|damen)\b|\(w\)|\bfem\.?$", re.I)


def is_women_competition(name: object) -> bool:
    return bool(isinstance(name, str) and _WOMEN_RE.search(name))


def is_women_team(names: Iterable[str]) -> bool:
    return any(isinstance(n, str) and _TEAM_RE.search(n) for n in names or [])


def comp_sql(names: Sequence[str], alias: str = "m") -> str:
    """Trecho SQL ' AND ...' que deixa só as competições do mesmo gênero do time (pela coluna competition_name)."""
    col = f"LOWER(COALESCE({alias}.competition_name, ''))" if alias else "LOWER(COALESCE(competition_name, ''))"
    any_women = "(" + " OR ".join(f"{col} LIKE '{p}'" for p in WOMEN_LIKE) + ")"
    return f" AND {any_women}" if is_women_team(names) else f" AND NOT {any_women}"


def keep_same_gender(df, names: Sequence[str], col: str = "competition_name"):
    """Mesma regra para um DataFrame já carregado."""
    if df is None or getattr(df, "empty", True) or col not in df:
        return df
    w = df[col].map(is_women_competition)
    return df[w] if is_women_team(names) else df[~w]
