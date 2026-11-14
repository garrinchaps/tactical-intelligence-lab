"""
Mapeamento de identificadores entre fontes (dim_teams, dim_players e tabelas-ponte team_ids/player_ids).

Cada fonte chama o mesmo clube de um jeito: "Man United" (football-data.co.uk), "Manchester United" (StatsBomb),
"Manchester United FC" (football-data.org), id 985 (Transfermarkt), 89 (Understat), 33 (API-Football).
O resolvedor cria UMA chave canônica por clube (`team_key`) e por atleta (`player_key`) e guarda a ligação com o
identificador de cada fonte, para cruzar dados sem conflito.

Regras (em ordem): apelidos conhecidos → nome normalizado (sem acento, sem sufixos como FC/EC/SC) →
semelhança alta (≥ 0,92) dentro do mesmo país. Atletas: nome normalizado + clube (+ data de nascimento quando
a fonte informa). O que não tiver correspondência vira uma chave própria — nunca é fundido por palpite fraco.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

SUFFIXES = {"fc", "cf", "sc", "ec", "ac", "afc", "cfc", "fk", "sk", "bk", "if", "club", "clube", "futebol", "de", "da",
            "do", "the", "calcio", "sv", "ss", "ssc", "as", "us", "rc", "cd", "ud", "sd", "ca", "se", "cr", "esporte",
            "sociedade", "esportiva", "associacao", "regatas", "foot", "ball", "football", "1", "e.c.", "f.c."}
ALIASES: Dict[str, str] = {
    # Inglaterra
    "man united": "manchester united", "man utd": "manchester united", "manchester utd": "manchester united",
    "man city": "manchester city", "spurs": "tottenham hotspur", "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers", "nott'm forest": "nottingham forest",
    "nottm forest": "nottingham forest", "newcastle": "newcastle united", "west ham": "west ham united",
    "brighton": "brighton hove albion", "brighton and hove albion": "brighton hove albion", "leicester": "leicester city",
    "leeds": "leeds united", "sheffield united": "sheffield united", "sheffield utd": "sheffield united",
    "west brom": "west bromwich albion", "ipswich": "ipswich town", "luton": "luton town", "norwich": "norwich city",
    # Espanha / Itália / Alemanha / França / Portugal
    "ath madrid": "atletico madrid", "atletico de madrid": "atletico madrid", "club atletico de madrid": "atletico madrid",
    "ath bilbao": "athletic club", "athletic bilbao": "athletic club", "betis": "real betis", "sociedad": "real sociedad",
    "celta": "celta vigo", "rc celta": "celta vigo", "espanol": "espanyol", "vallecano": "rayo vallecano",
    "inter": "internazionale", "inter milan": "internazionale", "milan": "ac milan", "roma": "as roma",
    "bayern munich": "bayern munchen", "fc bayern munchen": "bayern munchen", "dortmund": "borussia dortmund",
    "m'gladbach": "borussia monchengladbach", "monchengladbach": "borussia monchengladbach", "ein frankfurt": "eintracht frankfurt",
    "leverkusen": "bayer leverkusen", "bayer 04 leverkusen": "bayer leverkusen", "rb leipzig": "rasenballsport leipzig",
    "leipzig": "rasenballsport leipzig", "paris sg": "paris saint-germain", "psg": "paris saint-germain",
    "paris saint germain": "paris saint-germain", "st etienne": "saint-etienne", "sporting cp": "sporting lisbon",
    "sp lisbon": "sporting lisbon", "sporting": "sporting lisbon", "fc porto": "porto", "sl benfica": "benfica",
    # Brasil
    "atletico-mg": "atletico mineiro", "atletico mg": "atletico mineiro", "atl mineiro": "atletico mineiro",
    "clube atletico mineiro": "atletico mineiro", "athletico-pr": "athletico paranaense", "athletico pr": "athletico paranaense",
    "atletico-pr": "athletico paranaense", "atletico paranaense": "athletico paranaense", "vasco": "vasco da gama",
    "cr vasco da gama": "vasco da gama", "rb bragantino": "bragantino", "red bull bragantino": "bragantino",
    "sport recife": "sport", "sport club do recife": "sport", "america-mg": "america mineiro", "america mg": "america mineiro",
    "sao paulo fc": "sao paulo", "se palmeiras": "palmeiras", "sc corinthians paulista": "corinthians",
    "cr flamengo": "flamengo", "botafogo-rj": "botafogo", "botafogo rj": "botafogo", "gremio fbpa": "gremio",
    "sc internacional": "internacional", "ec bahia": "bahia", "ec vitoria": "vitoria", "fortaleza ec": "fortaleza",
    "ceara sc": "ceara", "cuiaba ec": "cuiaba", "goias ec": "goias", "chapecoense-sc": "chapecoense",
    # seleções
    "korea republic": "south korea", "ir iran": "iran", "usa": "united states", "türkiye": "turkey", "turkiye": "turkey",
}


def norm(text: object) -> str:
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower().replace("&", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' \-]", " ", t)).strip()


def team_core(name: object) -> str:
    """Nome normalizado sem sufixos institucionais, já com apelidos resolvidos."""
    n = norm(name)
    n = ALIASES.get(n, n)
    toks = [t for t in re.split(r"[\s\-]+", n) if t and t not in SUFFIXES]
    core = " ".join(toks) or n
    return ALIASES.get(core, core)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")


# ------------------------------------------------------------------------ equipes
SOURCE_COLS = ["statsbomb", "wyscout", "api_football", "football_data", "espn", "fdcouk", "understat",
               "transfermarkt", "api_futebol", "basedosdados", "simonetti"]


def resolve_teams(records: Iterable[Dict[str, object]], threshold: float = 0.92) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    records: dicts com fonte, id_fonte (pode ser vazio), nome, pais (opcional).
    Devolve (dim_teams, team_ids).
    """
    rows = pd.DataFrame(list(records))
    if rows.empty:
        return pd.DataFrame(), pd.DataFrame()
    rows["pais"] = rows.get("pais", "").fillna("") if "pais" in rows else ""
    rows["core"] = rows["nome"].map(team_core)
    rows = rows[rows["core"] != ""]
    # 1) agrupa por núcleo do nome; 2) funde núcleos muito parecidos do mesmo país (ou sem país informado)
    cores = rows.groupby("core")["pais"].agg(lambda s: next((x for x in s if x), "")).to_dict()
    parent = {c: c for c in cores}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c
    by_first: Dict[str, List[str]] = {}
    for c in cores:
        by_first.setdefault(c[:3], []).append(c)
    for group in by_first.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                pa, pb = cores[a], cores[b]
                if pa and pb and norm(pa) != norm(pb):
                    continue
                if SequenceMatcher(None, a, b).ratio() >= threshold:
                    parent[find(b)] = find(a)
    rows["team_key"] = rows["core"].map(lambda c: slug(find(c)))
    ids = rows[["team_key", "fonte", "id_fonte", "nome", "pais"]].drop_duplicates().reset_index(drop=True)
    ids["id_fonte"] = ids["id_fonte"].astype(str).replace({"nan": "", "None": ""})

    def canonical_name(g: pd.DataFrame) -> str:
        pref = ["statsbomb", "api_football", "understat", "transfermarkt", "football_data", "wyscout", "espn", "fdcouk"]
        for src in pref:
            n = g.loc[g["fonte"] == src, "nome"]
            if not n.empty:
                return str(n.mode().iloc[0])
        return str(g["nome"].mode().iloc[0])
    dims = []
    for key, g in ids.groupby("team_key"):
        d = {"team_key": key, "nome": canonical_name(g), "pais": next((p for p in g["pais"] if p), ""),
             "nomes_alternativos": " | ".join(sorted(set(map(str, g["nome"])))), "n_fontes": int(g["fonte"].nunique())}
        for src in SOURCE_COLS:
            v = g.loc[(g["fonte"] == src) & (g["id_fonte"] != ""), "id_fonte"]
            d[f"{src}_id"] = ";".join(sorted(set(map(str, v)))) if not v.empty else ""
        dims.append(d)
    return pd.DataFrame(dims).sort_values(["n_fontes", "nome"], ascending=[False, True]).reset_index(drop=True), ids


def team_key_lookup(team_ids: pd.DataFrame) -> Dict[Tuple[str, str], str]:
    """(fonte, nome) → team_key, para traduzir rapidamente o nome que uma fonte usa."""
    return {(r.fonte, str(r.nome)): r.team_key for r in team_ids.itertuples()}


# ------------------------------------------------------------------------ atletas
def player_core(name: object) -> str:
    return " ".join(t for t in re.split(r"[\s\-\.]+", norm(name)) if len(t) > 1)


def resolve_players(records: Iterable[Dict[str, object]]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    records: fonte, id_fonte, nome, team_key (opcional), nascimento (opcional, AAAA-MM-DD).
    Mesma pessoa = mesmo nome normalizado + mesmo clube, ou mesmo nome + mesma data de nascimento.
    Nomes completos da StatsBomb ("Lionel Andrés Messi Cuccittini") casam com o nome curto quando primeiro e
    último sobrenome do curto aparecem no completo e o clube coincide.
    """
    rows = pd.DataFrame(list(records))
    if rows.empty:
        return pd.DataFrame(), pd.DataFrame()
    for c in ("team_key", "nascimento", "id_fonte"):
        if c not in rows:
            rows[c] = ""
    rows = rows.fillna({"team_key": "", "nascimento": "", "id_fonte": ""})
    rows["core"] = rows["nome"].map(player_core)
    rows = rows[rows["core"] != ""].copy()
    # chave base: com nascimento, nome+nascimento; senão nome+clube
    rows["player_key"] = [f"{slug(c)}_{n}" if n else f"{slug(c)}_{t or 'sem-clube'}"
                          for c, n, t in zip(rows["core"], rows["nascimento"].astype(str).str[:10], rows["team_key"])]
    # quem tem nascimento (ex.: Transfermarkt) "adota" as linhas sem nascimento do mesmo nome+clube
    with_dob = rows[rows["nascimento"].astype(str).str.len() >= 8]
    index = {(c, t): k for c, t, k in zip(with_dob["core"], with_dob["team_key"], with_dob["player_key"]) if t}
    short = {}
    for c, t, k in zip(with_dob["core"], with_dob["team_key"], with_dob["player_key"]):
        toks = c.split()
        if len(toks) >= 2 and t:
            short.setdefault(t, []).append((toks[0], toks[-1], k))

    def adopt(r):
        if str(r.nascimento)[:4].isdigit():
            return r.player_key
        k = index.get((r.core, r.team_key))
        if k:
            return k
        toks = r.core.split()
        for first, last, key in short.get(r.team_key, []):     # nome longo contém primeiro e último do curto
            if first in toks and last in toks:
                return key
        return r.player_key
    rows["player_key"] = [adopt(r) for r in rows.itertuples()]
    ids = rows[["player_key", "fonte", "id_fonte", "nome", "team_key", "nascimento"]].drop_duplicates().reset_index(drop=True)
    ids["id_fonte"] = ids["id_fonte"].astype(str).replace({"nan": "", "None": ""})
    dims = []
    for key, g in ids.groupby("player_key"):
        tm = g.loc[g["fonte"] == "transfermarkt", "nome"]
        d = {"player_key": key, "nome": str(tm.iloc[0] if not tm.empty else min(g["nome"], key=len)),
             "nome_completo": str(max(g["nome"], key=len)),
             "nascimento": next((str(x)[:10] for x in g["nascimento"] if str(x)[:4].isdigit()), ""),
             "team_key": next((t for t in g["team_key"] if t), ""), "n_fontes": int(g["fonte"].nunique())}
        for src in SOURCE_COLS:
            v = g.loc[(g["fonte"] == src) & (g["id_fonte"] != ""), "id_fonte"]
            d[f"{src}_id"] = ";".join(sorted(set(map(str, v)))) if not v.empty else ""
        dims.append(d)
    return pd.DataFrame(dims), ids
