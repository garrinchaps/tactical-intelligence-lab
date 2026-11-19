"""
Rodada 20 — apelidos de times APRENDIDOS pelos jogos em comum entre as fontes.

Problema: a ESPN chama de "FC Cologne" o time que a FotMob chama de "1. FC Köln" (e "Bayern Munich" × "Bayern
München", "Inter Miami CF" × "Inter Miami"…). A comparação de nomes não liga os dois e o próximo jogo do Bayern
mostrava o rival com "0 jogos".

Regra (conservadora): duas fontes DIFERENTES com um jogo na mesma data (±1 dia), MESMO placar e um dos times com o
mesmo nome normalizado → os nomes diferentes do outro time são o mesmo clube. Só vira apelido com ≥ 2 jogos assim
(uma coincidência isolada não basta) e nunca junta masculino com feminino, sub-20 ou time B.

    python -m src.data_hub.team_alias          # recalcula (o processo de fundo refaz 1×/dia)
"""

from __future__ import annotations

import re
import threading
import time
from typing import Dict, List, Set

import pandas as pd

DDL = ("CREATE TABLE IF NOT EXISTS team_aliases (name TEXT NOT NULL, other TEXT NOT NULL, evidence INTEGER, "
       "built_at TEXT, PRIMARY KEY (name, other))")
MIN_EVIDENCE = 2
_TAG = re.compile(r"\b(wfc|women|womens|ladies|feminino|femenino|f[eé]minin|fem|w|u-?\d{2}|sub-?\d{2}|ii|b|reserves?)\b"
                  r"|\(w\)", re.I)
_LOCK = threading.Lock()
_GROUPS: Dict[str, Dict[str, Set[str]]] = {}


def _kind(name: str) -> str:
    m = _TAG.search(str(name or ""))
    return m.group(0).lower() if m else ""


def learn(matches: pd.DataFrame, min_evidence: int = MIN_EVIDENCE) -> pd.DataFrame:
    """matches: match_date, data_source, home_team_name, away_team_name, home_score, away_score → pares (a, b, n)."""
    from src.data_lake.ids import team_core

    if matches is None or matches.empty:
        return pd.DataFrame(columns=["name", "other", "evidence"])
    m = matches.dropna(subset=["home_score", "away_score", "home_team_name", "away_team_name"]).copy()
    m["d"] = pd.to_datetime(m["match_date"].astype(str).str[:10], errors="coerce")
    m = m.dropna(subset=["d"])
    names = pd.unique(pd.concat([m["home_team_name"], m["away_team_name"]]).astype(str))
    core = {n: team_core(n) for n in names}
    m["hc"] = m["home_team_name"].map(core)
    m["ac"] = m["away_team_name"].map(core)
    m["hs"] = pd.to_numeric(m["home_score"], errors="coerce")
    m["as_"] = pd.to_numeric(m["away_score"], errors="coerce")
    base = m[["d", "data_source", "home_team_name", "away_team_name", "hc", "ac", "hs", "as_"]]
    pairs = []
    for shift in (0, 1):                                  # mesma data ou um dia de diferença (fuso/horário)
        other = base.copy()
        other["d"] = other["d"] + pd.Timedelta(days=shift)
        for fixed, free in (("hc", "away_team_name"), ("ac", "home_team_name")):
            j = base.merge(other, on=["d", fixed, "hs", "as_"], suffixes=("", "_o"))
            j = j[(j["data_source"] != j["data_source_o"]) & (j[free] != j[f"{free}_o"])]
            if j.empty:
                continue
            fc = "ac" if free == "away_team_name" else "hc"
            j = j[j[fc] != j[f"{fc}_o"]]                  # nomes que a normalização já liga não precisam de apelido
            pairs.append(pd.DataFrame({"name": j[free].astype(str), "other": j[f"{free}_o"].astype(str),
                                       "d": j["d"]}))
    if not pairs:
        return pd.DataFrame(columns=["name", "other", "evidence"])
    p = pd.concat(pairs, ignore_index=True)
    p = p[p["name"].map(_kind) == p["other"].map(_kind)]  # masculino × feminino / sub-20 / B nunca se juntam
    lo = p["name"].where(p["name"] < p["other"], p["other"])
    hi = p["other"].where(p["name"] < p["other"], p["name"])
    games = pd.DataFrame({"name": lo, "other": hi, "d": p["d"].dt.strftime("%Y-%m-%d")})
    games = games.drop_duplicates()                      # cada JOGO conta uma vez (a junção vê os dois sentidos)
    cnt = games[["name", "other"]].value_counts().reset_index(name="evidence")
    cnt = cnt[cnt["evidence"] >= min_evidence]
    return cnt[["name", "other", "evidence"]].reset_index(drop=True)


def build(db, years: int = 4) -> Dict[str, int]:
    since = f"{time.localtime().tm_year - years}-01-01"
    with db.connect() as conn:
        m = pd.read_sql_query("SELECT match_date, data_source, home_team_name, away_team_name, home_score, away_score "
                              "FROM matches WHERE match_date >= ? AND COALESCE(data_source,'') NOT IN ('simulated','upload')",
                              conn, params=[since])
    pairs = learn(m)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute("DELETE FROM team_aliases")
        conn.executemany("INSERT OR REPLACE INTO team_aliases VALUES (?,?,?,?)",
                         [(r.name, r.other, int(r.evidence), stamp) for r in pairs.itertuples()])
    with _LOCK:
        _GROUPS.clear()
    return {"pares": int(len(pairs)), "jogos_lidos": int(len(m))}


def _load(db) -> Dict[str, Set[str]]:
    key = str(getattr(db, "db_path", ""))
    with _LOCK:
        if key in _GROUPS:
            return _GROUPS[key]
    try:
        with db.connect() as conn:
            rows = conn.execute("SELECT name, other FROM team_aliases").fetchall()
    except Exception:
        rows = []
    parent: Dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in rows:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups: Dict[str, Set[str]] = {}
    for n in list(parent):
        groups.setdefault(find(n), set()).add(n)
    out = {n: g for g in groups.values() if len(g) <= 12 for n in g}   # grupo gigante = ligação errada: ignora
    with _LOCK:
        _GROUPS[key] = out
    return out


def aliases_of(db, name: str) -> List[str]:
    """Todos os nomes aprendidos para o mesmo clube (inclui o próprio)."""
    g = _load(db).get(str(name))
    return sorted(g) if g else [str(name)]


def main() -> None:
    from src.data_hub.db import DataHubDB

    t0 = time.time()
    r = build(DataHubDB())
    print(f"Apelidos de times aprendidos: {r['pares']} pares a partir de {r['jogos_lidos']:,} jogos em "
          f"{time.time() - t0:.0f} s.".replace(",", "."))


if __name__ == "__main__":
    main()
