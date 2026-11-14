"""
Understat → catálogo: o xG de cada jogo vira estatística da partida e o mapa de chutes fica a um clique.

* Para cada jogo do Understat (2014/15 em diante, 6 ligas), procura a MESMA partida no catálogo (data ±1 dia e
  as duas equipes pelo núcleo do nome). Achou: grava xG (e gols) como estatísticas dela — um jogo que era
  "só placar" passa a ter números. Não achou: cria a partida a partir do próprio Understat (fonte "understat").
* `ensure_shots(match_id)` baixa as finalizações (posição, xG, autor, assistência) de UMA partida na hora
  em que ela é aberta, e guarda em data/lake (não baixa de novo).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Optional

import pandas as pd

from src.data_hub.registry import DataLevel, to_internal_id

COUNTRY = {"Premier League": "England", "La Liga": "Spain", "Bundesliga": "Germany", "Serie A": "Italy",
           "Ligue 1": "France", "Russian Premier League": "Russia"}
LINKS = "us_links"


def _stats_rows(mid: int, home: str, away: str, r) -> List[tuple]:
    rows = []
    for team, xg, g in ((home, r.xg_mandante, r.gols_mandante), (away, r.xg_visitante, r.gols_visitante)):
        rows.append((int(mid), team, "xg", "xG (Understat)", float(xg), f"{float(xg):.2f}"))
    return rows


def understat_into_catalog(db, lake, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
    from src.data_hub.service import _same
    from src.data_lake.ids import team_core

    say = progress or (lambda m: None)
    if not lake.exists("us_partidas"):
        return {"us_ligados": 0, "us_novos": 0}
    us = lake.read("us_partidas").drop_duplicates("understat_id")
    us["data"] = us["data"].astype(str).str[:10]
    lo = (pd.to_datetime(us["data"]).min() - pd.Timedelta(days=1)).date().isoformat()
    hi = (pd.to_datetime(us["data"]).max() + pd.Timedelta(days=1)).date().isoformat()
    with db.connect() as conn:
        cat = pd.read_sql_query(
            "SELECT match_id, data_source, data_level, match_date, home_team_name, away_team_name FROM matches "
            "WHERE match_date BETWEEN ? AND ? AND data_source != 'understat'", conn, params=(lo, hi))
        existing = {int(x[0]) for x in conn.execute("SELECT match_id FROM matches WHERE data_source = 'understat'")}
    by_day = defaultdict(list)
    for r in cat.itertuples(index=False):
        by_day[str(r.match_date)[:10]].append((int(r.match_id), team_core(r.home_team_name), team_core(r.away_team_name),
                                                r.home_team_name, r.away_team_name, r.data_level))
    stats, links, new_recs, promote = [], [], [], []
    for r in us.itertuples(index=False):
        h, a = team_core(r.mandante), team_core(r.visitante)
        d = pd.Timestamp(r.data)
        hit = None
        for day in (d, d - pd.Timedelta(days=1), d + pd.Timedelta(days=1)):
            for c in by_day.get(day.date().isoformat(), []):
                if _same(c[1], h) and _same(c[2], a):
                    hit = c
                    break
            if hit:
                break
        if hit:
            mid, _, _, hn, an, lvl = hit
            stats += _stats_rows(mid, hn, an, r)
            links.append({"match_id": mid, "understat_id": int(r.understat_id)})
            if lvl == DataLevel.RESULT:
                promote.append(mid)
        else:
            mid = to_internal_id("understat", int(r.understat_id))
            if mid in existing:                      # criada numa rodada anterior: só atualiza o xG
                stats += _stats_rows(mid, r.mandante, r.visitante, r)
                links.append({"match_id": mid, "understat_id": int(r.understat_id)})
                continue
            new_recs.append({"match_id": mid, "home_team_name": r.mandante, "away_team_name": r.visitante,
                             "match_date": r.data, "home_score": int(r.gols_mandante), "away_score": int(r.gols_visitante),
                             "competition_name": r.liga, "season_name": r.temporada, "country_name": COUNTRY.get(r.liga, ""),
                             "status": "FT", "data_source": "understat", "data_level": DataLevel.BOXSCORE,
                             "source_match_id": int(r.understat_id)})
            stats += _stats_rows(mid, r.mandante, r.visitante, r)
            links.append({"match_id": mid, "understat_id": int(r.understat_id)})
    if new_recs:
        db.upsert_matches(new_recs)
    with db.connect() as conn:
        conn.executemany("INSERT OR REPLACE INTO match_team_stats (match_id, team_name, stat_key, stat_label, value, "
                         "display_value) VALUES (?, ?, ?, ?, ?, ?)", stats)
        if promote:
            conn.executemany("UPDATE matches SET data_level = 'BOXSCORE' WHERE match_id = ? AND data_level = 'RESULT'",
                             [(m,) for m in promote])
    if links:
        lake.write(LINKS, pd.DataFrame(links).drop_duplicates(), source="Understat", connector="understat_link")
    n_own = sum(1 for l in links if l["match_id"] in existing)
    out = {"us_ligados": len(links) - len(new_recs) - n_own, "us_novos": len(new_recs), "us_promovidos": len(promote)}
    say(f"  understat → catálogo: {out['us_ligados']} jogos ganharam xG, {out['us_novos']} jogos novos, "
        f"{out['us_promovidos']} deixaram de ser 'só placar'")
    return out


def understat_id_for(match_id: int, lake) -> Optional[int]:
    from src.data_hub.registry import SOURCES

    mid = int(match_id)
    off = SOURCES["understat"].id_offset
    if mid >= off:
        return mid - off
    for name, col in ((LINKS, "understat_id"), ("match_links", "id_fonte")):
        if lake.exists(name):
            l = lake.read(name)
            if name == "match_links":
                l = l[l["fonte"] == "understat"]
            hit = l[l["match_id"].astype(str) == str(mid)]
            if not hit.empty:
                return int(hit[col].iloc[0])
    return None


def ensure_shots(match_id: int, lake=None, provider=None) -> pd.DataFrame:
    """Finalizações do Understat desta partida; baixa na hora (1 requisição) se ainda não estiverem no lake."""
    from src.data_lake.lake import Lake

    lake = lake or Lake()
    uid = understat_id_for(match_id, lake)
    if uid is None:
        return pd.DataFrame()
    if lake.exists("us_finalizacoes"):
        s = lake.read("us_finalizacoes")
        got = s[s["understat_id"].astype(str) == str(uid)]
        if not got.empty:
            return got.sort_values("minuto")
    try:
        if provider is None:
            from src.data_hub.sources.understat import UnderstatProvider

            provider = UnderstatProvider()
        sf = provider.shots_frame(provider.match_shots(uid))
    except Exception:
        return pd.DataFrame()
    if sf.empty:
        return sf
    lake.upsert("us_finalizacoes", sf, ["understat_id", "minuto", "jogador", "xg"], source="Understat",
                connector="UnderstatProvider")
    return sf.sort_values("minuto")
