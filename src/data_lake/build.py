"""
Monta a camada unificada a partir de tudo que está no banco e no lake:

* dim_teams / team_ids     — uma chave por clube/seleção e o id que cada fonte usa;
* dim_players / player_ids — uma chave por atleta e o id de cada fonte;
* match_links              — a mesma partida em fontes diferentes (catálogo do app ↔ Understat ↔ Transfermarkt);
* fato_partidas            — visão única de partidas com o melhor nível de dado disponível e as chaves canônicas.

Roda no fim de cada sincronização diária (e pode ser chamado à mão: python -m src.data_lake.build).
"""

from __future__ import annotations

import sqlite3
from typing import Callable, Dict, List, Optional

import pandas as pd

from src.data_lake.ids import resolve_players, resolve_teams, team_key_lookup
from src.data_lake.lake import Lake


def _sql(db, q: str) -> pd.DataFrame:
    with db.connect() as conn:
        try:
            return pd.read_sql_query(q, conn)
        except Exception:
            return pd.DataFrame()


def team_records(db, lake: Lake) -> List[Dict[str, object]]:
    recs: List[Dict[str, object]] = []
    m = _sql(db, "SELECT data_source, country_name, home_team_id, home_team_name, away_team_id, away_team_name FROM matches")
    for side in ("home", "away"):
        if m.empty:
            break
        t = m[["data_source", "country_name", f"{side}_team_id", f"{side}_team_name"]].drop_duplicates()
        for r in t.itertuples(index=False):
            src, country, tid, name = r
            recs.append({"fonte": src, "id_fonte": "" if not tid else str(int(tid)) if str(tid).isdigit() else str(tid),
                         "nome": name, "pais": country or ""})
    if lake.exists("tm_clubes"):
        for r in lake.read("tm_clubes").itertuples():
            recs.append({"fonte": "transfermarkt", "id_fonte": str(r.transfermarkt_id), "nome": r.nome, "pais": getattr(r, "pais", "") or ""})
    if lake.exists("us_partidas"):
        u = lake.read("us_partidas")
        for side in ("mandante", "visitante"):
            for r in u[[side, f"{side}_understat_id"]].drop_duplicates().itertuples(index=False):
                recs.append({"fonte": "understat", "id_fonte": str(r[1]), "nome": r[0], "pais": ""})
    for name, src in (("af_classificacao", "api_futebol"), ("apf_classificacao", "api_football")):
        if lake.exists(name):
            t = lake.read(name)
            idc = "api_futebol_id" if src == "api_futebol" else "api_football_id"
            for r in t[["equipe", idc]].drop_duplicates().itertuples(index=False):
                recs.append({"fonte": src, "id_fonte": str(r[1]), "nome": r[0], "pais": "Brazil" if src == "api_futebol" else ""})
    if lake.exists("bd_brasileirao"):
        b = lake.read("bd_brasileirao", None)
        for col in ("mandante", "visitante"):
            if col in b:
                for n in b[col].dropna().unique():
                    recs.append({"fonte": "basedosdados", "id_fonte": "", "nome": n, "pais": "Brazil"})
    for name in simonetti_tables(lake):
        from src.data_hub.sources.simonetti import player_team_columns

        d = lake.read(name)
        _, tcol = player_team_columns(d)
        if tcol:
            for n in d[tcol].dropna().astype(str).unique():
                recs.append({"fonte": "simonetti", "id_fonte": "", "nome": n, "pais": ""})
    return [r for r in recs if r["nome"]]


def simonetti_tables(lake: Lake) -> List[str]:
    t = lake.tables()
    return [n for n in t["tabela"].tolist() if n.startswith("sm_") and n != "sm_tabelas_html"] if not t.empty else []


def player_records(db, lake: Lake, tkey: Dict, tm_club_key: Dict[str, str]) -> List[Dict[str, object]]:
    recs: List[Dict[str, object]] = []
    ev = _sql(db, "SELECT DISTINCT e.player_id, e.player_name, e.team_name, m.data_source FROM events e "
                  "JOIN matches m ON m.match_id = e.match_id WHERE e.player_name IS NOT NULL")
    for r in ev.itertuples(index=False):
        recs.append({"fonte": r.data_source, "id_fonte": "" if pd.isna(r.player_id) else str(int(r.player_id)),
                     "nome": r.player_name, "team_key": tkey.get((r.data_source, r.team_name), "")})
    ps = _sql(db, "SELECT DISTINCT s.player_name, s.team_name, m.data_source FROM match_player_stats s "
                  "JOIN matches m ON m.match_id = s.match_id")
    for r in ps.itertuples(index=False):
        recs.append({"fonte": r.data_source, "id_fonte": "", "nome": r.player_name,
                     "team_key": tkey.get((r.data_source, r.team_name), "")})
    if lake.exists("tm_jogadores"):
        tp = lake.read("tm_jogadores")
        recent = tp[pd.to_numeric(tp.get("ultima_temporada"), errors="coerce").fillna(0) >= 2018] if "ultima_temporada" in tp else tp
        for r in recent.itertuples():
            recs.append({"fonte": "transfermarkt", "id_fonte": str(r.transfermarkt_id), "nome": r.nome,
                         "nascimento": str(getattr(r, "nascimento", "") or "")[:10],
                         "team_key": tm_club_key.get(str(getattr(r, "clube_id", "")), "")})
    if lake.exists("us_jogadores"):
        up = lake.read("us_jogadores")
        for r in up[["understat_id", "nome", "clube"]].drop_duplicates().itertuples(index=False):
            club = str(r.clube).split(",")[-1].strip()     # jogador transferido na temporada: "Time A,Time B"
            recs.append({"fonte": "understat", "id_fonte": str(r.understat_id), "nome": r.nome,
                         "team_key": tkey.get(("understat", club), "")})
    from src.data_hub.sources.simonetti import player_team_columns

    for name in simonetti_tables(lake):
        d = lake.read(name)
        pcol, tcol = player_team_columns(d)
        if pcol:
            sub = d[[pcol] + ([tcol] if tcol else [])].dropna(subset=[pcol]).drop_duplicates()
            for r in sub.itertuples(index=False):
                recs.append({"fonte": "simonetti", "id_fonte": "", "nome": r[0],
                             "team_key": tkey.get(("simonetti", str(r[1])), "") if tcol else ""})
    return recs


class KeyLookup(dict):
    """(fonte, nome) → team_key; se a fonte usar uma grafia que não estava no cadastro, cai no núcleo do nome."""

    def __init__(self, tkey: Dict, team_ids: pd.DataFrame):
        super().__init__(tkey)
        from src.data_lake.ids import team_core

        self._core = {}
        for r in team_ids.itertuples():
            self._core.setdefault(team_core(r.nome), r.team_key)
        self._tc = team_core

    def get(self, k, default=""):
        v = super().get(k)
        return v if v else self._core.get(self._tc(k[1]), default)


def match_links(db, lake: Lake, tkey: Dict) -> pd.DataFrame:
    """Liga partidas do Understat e do Transfermarkt às do catálogo por data + chaves canônicas das equipes."""
    cat = _sql(db, "SELECT match_id, data_source, data_level, match_date, home_team_name, away_team_name FROM matches")
    if cat.empty:
        return pd.DataFrame()
    cat["hk"] = [tkey.get((s, h), "") for s, h in zip(cat["data_source"], cat["home_team_name"])]
    cat["ak"] = [tkey.get((s, a), "") for s, a in zip(cat["data_source"], cat["away_team_name"])]
    cat = cat[(cat["hk"] != "") & (cat["ak"] != "")]
    links = []
    for name, src, idc in (("us_partidas", "understat", "understat_id"), ("tm_jogos", "transfermarkt", "transfermarkt_id")):
        if not lake.exists(name):
            continue
        o = lake.read(name)
        o["hk"] = [tkey.get((src, h), "") for h in o["mandante"]]
        o["ak"] = [tkey.get((src, a), "") for a in o["visitante"]]
        o["data"] = o["data"].astype(str).str[:10]
        j = cat.merge(o[["data", "hk", "ak", idc]], left_on=["match_date", "hk", "ak"], right_on=["data", "hk", "ak"])
        for r in j.itertuples(index=False):
            links.append({"match_id": int(r.match_id), "fonte": src, "id_fonte": str(getattr(r, idc))})
    return pd.DataFrame(links).drop_duplicates() if links else pd.DataFrame(columns=["match_id", "fonte", "id_fonte"])


def build_all(db=None, lake: Optional[Lake] = None, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
    from src.data_hub.db import DataHubDB

    say = progress or (lambda m: None)
    db = db or DataHubDB()
    lake = lake or Lake(sqlite_path=db.db_path)
    dim_t, tids = resolve_teams(team_records(db, lake))
    if dim_t.empty:
        return {"dim_teams": 0, "dim_players": 0, "links": 0}
    tkey = KeyLookup(team_key_lookup(tids), tids)
    lake.write("dim_teams", dim_t, source="Tactical Intelligence Lab", connector="IdentityResolver")
    lake.write("team_ids", tids, source="Tactical Intelligence Lab", connector="IdentityResolver")
    tm_club_key = {str(r.id_fonte): r.team_key for r in tids[tids["fonte"] == "transfermarkt"].itertuples()}
    dim_p, pids = resolve_players(player_records(db, lake, tkey, tm_club_key))
    if not dim_p.empty:
        lake.write("dim_players", dim_p, source="Tactical Intelligence Lab", connector="IdentityResolver")
        lake.write("player_ids", pids, source="Tactical Intelligence Lab", connector="IdentityResolver")
    links = match_links(db, lake, tkey)
    lake.write("match_links", links, source="Tactical Intelligence Lab", connector="IdentityResolver")
    out = {"dim_teams": len(dim_t), "times_em_2+_fontes": int((dim_t["n_fontes"] >= 2).sum()),
           "dim_players": len(dim_p), "atletas_em_2+_fontes": int((dim_p["n_fontes"] >= 2).sum()) if not dim_p.empty else 0,
           "links": len(links)}
    say(f"  camada unificada: {out}")
    out["updated"] = out["dim_teams"]
    return out


def shots_for_match(match_id: int, lake: Optional[Lake] = None) -> pd.DataFrame:
    """Finalizações (Understat) de uma partida do catálogo, se ela estiver ligada a uma partida Understat."""
    lake = lake or Lake()
    if not (lake.exists("match_links") and lake.exists("us_finalizacoes")):
        return pd.DataFrame()
    l = lake.read("match_links")
    u = l[(l["match_id"].astype(str) == str(int(match_id))) & (l["fonte"] == "understat")]
    if u.empty:
        return pd.DataFrame()
    s = lake.read("us_finalizacoes")
    return s[s["understat_id"].astype(str) == str(u["id_fonte"].iloc[0])].sort_values("minuto")


def market_values(lake: Optional[Lake] = None) -> pd.DataFrame:
    """player_key → valor de mercado atual (Transfermarkt), para cruzar com as estatísticas do app."""
    lake = lake or Lake()
    if not (lake.exists("player_ids") and lake.exists("tm_jogadores")):
        return pd.DataFrame()
    ids = lake.read("player_ids")
    tm = lake.read("tm_jogadores")[["transfermarkt_id", "valor_mercado_eur", "nascimento", "posicao"]]
    tm["transfermarkt_id"] = tm["transfermarkt_id"].astype(str)
    j = ids[ids["fonte"] == "transfermarkt"].merge(tm, left_on="id_fonte", right_on="transfermarkt_id")
    return ids.merge(j[["player_key", "valor_mercado_eur", "posicao"]].drop_duplicates("player_key"), on="player_key")


if __name__ == "__main__":
    print(build_all(progress=print))
