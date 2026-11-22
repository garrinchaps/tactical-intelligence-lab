"""Separa competições femininas e masculinas (o catálogo mistura as duas)."""

from __future__ import annotations

import os

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
    ex = df["extra_json"].fillna("").astype(str) if "extra_json" in df.columns else pd.Series("", index=df.index)
    # rodada 22: a expressão regular só roda nas linhas que falam de "gender" e nos NOMES distintos (milhares), não em
    # cada uma das ~300 mil linhas (era 1,6 s por leitura do catálogo)
    female_src = pd.Series(False, index=df.index)
    male_src = pd.Series(False, index=df.index)
    has_g = ex.str.contains('"gender"', regex=False)
    if has_g.any():
        female_src[has_g] = ex[has_g].str.contains(r'"gender":\s*"(?:female|feminino)"', regex=True)
        male_src[has_g] = ex[has_g].str.contains(r'"gender":\s*"(?:male|masculino)"', regex=True)
    rx = re.compile(FEMALE_RX.pattern, re.I)
    by_name = pd.Series(False, index=df.index)
    for col in ("competition_name", "home_team_name", "away_team_name"):
        if col not in df.columns:
            continue
        v = df[col].fillna("").astype(str)
        uniq = pd.unique(v)
        hit = {u for u in uniq if rx.search(" " + u + " ")}
        if hit:
            by_name |= v.isin(hit)
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
    """Trecho SQL ' AND ...' que deixa só as competições do mesmo gênero do time (pela coluna competition_name).
    Rodada 27: também tira as ligas NACIONAIS de outro país (Santos × Santos Laguna, Barcelona × Barcelona SC) —
    quando alguma fonte dá o mesmo nome a dois clubes, os jogos do outro não entram (ver `foreign_competitions`)."""
    col = f"LOWER(COALESCE({alias}.competition_name, ''))" if alias else "LOWER(COALESCE(competition_name, ''))"
    any_women = "(" + " OR ".join(f"{col} LIKE '{p}'" for p in WOMEN_LIKE) + ")"
    out = f" AND {any_women}" if is_women_team(names) else f" AND NOT {any_women}"
    foreign = foreign_competitions(names)
    if foreign:
        raw = f"COALESCE({alias}.competition_name, '')" if alias else "COALESCE(competition_name, '')"
        out += f" AND {raw} NOT IN (" + ", ".join("'" + str(c).replace("'", "''") + "'" for c in foreign) + ")"
    return out


COUNTRY_KEYS = [
    ("ec", ("equador", "ecuador", "ligapro")), ("uy", ("uruguai", "uruguay")), ("ar", ("argentina", "primera nacional")),
    ("cl", ("chile",)), ("co", ("colômbia", "colombia")), ("pe", ("peru", "liga 1")), ("py", ("paraguai", "paraguay")),
    ("bo", ("bolívia", "bolivia")), ("ve", ("venezuela",)), ("mx", ("liga mx", "méxico", "mexico")),
    ("us", ("mls", "usa", "estados unidos")), ("br", ("brasil", "brasileir", "copa do brasil", "paulist", "carioca",
                                                     "mineiro", "gaúcho", "serie a brazil")),
    ("es", ("la liga", "laliga", "copa del rey", "espanha", "spain", "segunda división", "la liga 2")),
    ("en", ("premier league", "championship", "fa cup", "efl", "england", "inglaterra")),
    ("it", ("serie a", "serie b", "coppa italia", "itália", "italy")), ("de", ("bundesliga", "dfb", "alemanha", "germany")),
    ("fr", ("ligue 1", "ligue 2", "coupe de france", "frança", "france")), ("pt", ("primeira liga", "liga portugal",
                                                                                 "taça de portugal", "portugal")),
    ("nl", ("eredivisie", "eerste divisie", "knvb")), ("tr", ("süper lig", "super lig", "turquia", "turkey")),
]


def comp_country(comp: str):
    c = str(comp or "").lower()
    if any(k in c for k in ("champions", "europa", "conference", "libertadores", "sul-americana", "sudamericana",
                            "mundial", "world", "amistoso", "friendl", "recopa", "supercopa da uefa", "super cup")):
        return None                                      # competição internacional: não diz o país
    return next((code for code, keys in COUNTRY_KEYS if any(k in c for k in keys)), None)


_FOREIGN_MEMO: dict = {}


def foreign_competitions(names: Sequence[str], db=None, ttl_s: float = 6 * 3600) -> list:
    """Ligas NACIONAIS de outro país em que um time com este nome aparece. O país do clube é o da MAIORIA dos seus
    jogos de liga nacional (≥ 60%; sem maioria clara, nada é tirado). Competição internacional (Libertadores,
    Champions, amistosos) nunca é tirada. Uma consulta por time, guardada 6 h no processo."""
    import time

    key = tuple(sorted({str(n) for n in names if n}))
    if not key or os.getenv("TIL_FILTRO_PAIS", "1") == "0":
        return []
    hit = _FOREIGN_MEMO.get(key)
    if hit and time.time() - hit[0] < ttl_s:
        return hit[1]
    out: list = []
    try:
        if db is None:
            from src.data_hub.db import DataHubDB

            db = DataHubDB()
        ph = ",".join("?" * len(key))
        with db.connect() as conn:
            rows = conn.execute(f"SELECT competition_name, COUNT(*) FROM matches WHERE home_team_name IN ({ph}) OR "
                                f"away_team_name IN ({ph}) GROUP BY competition_name", list(key) * 2).fetchall()
        by_c: dict = {}
        comp_cc = {}
        for comp, n in rows:
            cc = comp_country(comp)
            comp_cc[comp] = cc
            if cc:
                by_c[cc] = by_c.get(cc, 0) + int(n)
        tot = sum(by_c.values())
        if tot >= 10:
            home, n_home = max(by_c.items(), key=lambda t: t[1])
            if n_home / tot >= .6:
                out = sorted(c for c, cc in comp_cc.items() if c and cc and cc != home)
    except Exception:
        out = []
    _FOREIGN_MEMO[key] = (time.time(), out)
    return out


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

    out: set = set()
    try:
        # rodada 22: antes um GROUP BY juntando TODAS as linhas de jogadores com as partidas (3 s por tabela na base
        # grande). Agora: (1) os poucos jogos femininos; (2) quem jogou neles; (3) desses nomes, quem também aparece em
        # outro jogo (pelo índice de nome) — mesmo resultado, em frações de segundo.
        with db.connect() as conn:
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS _w_ids (match_id INTEGER PRIMARY KEY)")
            conn.execute("DELETE FROM _w_ids")
            # nomes de competição distintos (centenas) em vez de LIKE em cada uma das ~440 mil partidas
            comps = [c for (c,) in conn.execute("SELECT DISTINCT competition_name FROM matches")
                     if c and _WOMEN_RE.search(str(c).lower())]
            if comps:
                conn.executemany("INSERT OR IGNORE INTO _w_ids SELECT match_id FROM matches WHERE competition_name = ?",
                                 [(c,) for c in comps])
            women_names: set = set()
            men_names: set = set()
            for table in ("match_player_stats", "match_lineups"):
                try:
                    names = {r[0] for r in conn.execute(
                        f"SELECT DISTINCT player_name FROM {table} WHERE match_id IN (SELECT match_id FROM _w_ids)")
                        if r[0]}
                except Exception:
                    continue
                women_names |= names
                if not names:
                    continue
                conn.execute("CREATE TEMP TABLE IF NOT EXISTS _w_names (n TEXT PRIMARY KEY)")
                conn.execute("DELETE FROM _w_names")
                conn.executemany("INSERT OR IGNORE INTO _w_names VALUES (?)", [(n,) for n in names])
                men_names |= {r[0] for r in conn.execute(
                    f"SELECT DISTINCT t.player_name FROM {table} t JOIN _w_names w ON w.n = t.player_name "
                    f"WHERE t.match_id NOT IN (SELECT match_id FROM _w_ids)")}
        men = {player_core(n) for n in men_names}
        women = {player_core(n) for n in women_names - men_names}
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
