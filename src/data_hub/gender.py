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


# ----------------------------------------------------------------------------------------------- rodada 20
_WOMEN_PLAYERS: dict = {}


def women_only_players(db, ttl_s: float = 3600.0) -> set:
    """Núcleos de nome de quem SÓ aparece em competições femininas (números por jogador ou escalações).
    Servem para tirar jogadoras do mercado/elenco masculino quando a fonte deu o mesmo nome aos dois times
    ("Cruzeiro"). Quem aparece também em competição masculina NÃO entra (homônimo de verdade continua)."""
    import time as _t

    key = str(getattr(db, "db_path", ""))
    hit = _WOMEN_PLAYERS.get(key)
    if hit and _t.time() - hit[1] < ttl_s:
        return hit[0]
    from src.data_lake.ids import player_core

    col = "LOWER(COALESCE(m.competition_name, ''))"
    flag = "(" + " OR ".join(f"{col} LIKE '{p}'" for p in WOMEN_LIKE) + ")"
    out: set = set()
    try:
        with db.connect() as conn:
            rows = []
            for table in ("match_player_stats", "match_lineups"):
                try:
                    rows += conn.execute(f"SELECT t.player_name, MAX(CASE WHEN {flag} THEN 1 ELSE 0 END), "
                                         f"MIN(CASE WHEN {flag} THEN 1 ELSE 0 END) FROM {table} t JOIN matches m "
                                         f"ON m.match_id = t.match_id GROUP BY t.player_name").fetchall()
                except Exception:
                    continue
        men = {player_core(n) for n, mx, mn in rows if n and not (mx == 1 and mn == 1)}
        women = {player_core(n) for n, mx, mn in rows if n and mx == 1 and mn == 1}
        out = {c for c in women - men if c}
    except Exception:
        out = set()
    _WOMEN_PLAYERS[key] = (out, _t.time())
    return out


def drop_women_players(df, db, names=None, col: str = "nome"):
    """Tira do DataFrame (elenco/mercado de time MASCULINO) quem só jogou competições femininas."""
    if df is None or getattr(df, "empty", True) or col not in df:
        return df
    if names is not None and is_women_team(names):
        return df
    from src.data_lake.ids import player_core

    women = women_only_players(db)
    if not women:
        return df
    return df[~df[col].astype(str).map(player_core).isin(women)]
