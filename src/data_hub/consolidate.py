"""
Mesma partida em várias fontes: escolhe o valor de cada estatística por PRECEDÊNCIA DECLARADA e registra as
divergências — nunca tira média nem "suaviza" números diferentes.

    compare(db, match_id)  → tabela: estatística, time, fonte escolhida, valor, outras fontes e se divergem

A precedência segue o princípio de que fonte com eventos completos (contagem lance a lance) vem antes de fonte
agregada, e a fonte especializada vem antes da genérica (ex.: xG do OpenPlay/StatsBomb/Understat).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

EVENTS_FIRST = ["statsbomb", "wyscout", "openplay"]
AGGREGATED = ["brasileirao", "espn", "api_football", "fdcouk", "open_matchday", "cbf", "understat", "api_futebol"]
PRECEDENCE: Dict[str, List[str]] = {
    "xg": ["openplay", "statsbomb", "understat", "api_football", "espn"],
    "shots_total": EVENTS_FIRST + AGGREGATED,
    "shots_on_target": EVENTS_FIRST + AGGREGATED,
    "passes_total": EVENTS_FIRST + ["brasileirao", "espn", "api_football"],
    "pass_accuracy_pct": EVENTS_FIRST + ["brasileirao", "espn", "api_football"],
    "possession_pct": ["espn", "api_football", "brasileirao", "statsbomb", "wyscout", "openplay"],
    "corners": ["brasileirao", "espn", "api_football", "fdcouk", "open_matchday", "openplay", "statsbomb"],
    "fouls": ["brasileirao", "espn", "api_football", "fdcouk", "open_matchday", "openplay", "statsbomb"],
    "yellow_cards": ["brasileirao", "cbf", "espn", "api_football", "fdcouk", "open_matchday", "openplay", "statsbomb"],
    "red_cards": ["brasileirao", "cbf", "espn", "api_football", "fdcouk", "open_matchday", "openplay", "statsbomb"],
    "offsides": ["brasileirao", "espn", "api_football"],
    "ht_goals": ["fdcouk", "open_matchday", "espn", "api_football"],
}
DEFAULT = EVENTS_FIRST + AGGREGATED
TOLERANCE = {"possession_pct": 1.5, "pass_accuracy_pct": 1.5, "xg": 0.05}


def siblings(db, match_id: int, meta: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """A própria partida + a mesma partida em outras fontes (data ±1 dia, as duas equipes pelo núcleo do nome)."""
    from src.data_hub.service import _same
    from src.data_lake.ids import team_core

    meta = meta or db.get_match(int(match_id)) or {}
    d = str(meta.get("match_date") or "")[:10]
    h, a = team_core(meta.get("home_team_name")), team_core(meta.get("away_team_name"))
    out = [{"match_id": int(match_id), "data_source": meta.get("data_source"), "home": meta.get("home_team_name"),
            "away": meta.get("away_team_name"), "flip": False}]
    if not d or not h or not a:
        return out
    with db.connect() as conn:
        rows = conn.execute("SELECT match_id, data_source, home_team_name, away_team_name FROM matches WHERE match_id != ? "
                            "AND match_date BETWEEN date(?, '-1 day') AND date(?, '+1 day')", (int(match_id), d, d)).fetchall()
    for mid, src, rh, ra in rows:
        ch, ca = team_core(rh), team_core(ra)
        if _same(ch, h) and _same(ca, a):
            out.append({"match_id": int(mid), "data_source": src, "home": rh, "away": ra, "flip": False})
        elif _same(ch, a) and _same(ca, h):
            out.append({"match_id": int(mid), "data_source": src, "home": rh, "away": ra, "flip": True})
    return out


def compare(db, match_id: int, meta: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    meta = meta or db.get_match(int(match_id)) or {}
    sib = siblings(db, match_id, meta)
    if len(sib) < 2:
        return pd.DataFrame()
    vals: Dict[tuple, Dict[str, float]] = {}
    labels: Dict[str, str] = {}
    for s in sib:
        ts = db.load_boxscore(s["match_id"])["team_stats"]
        for r in ts.itertuples(index=False):
            side = "home" if r.team_name == s["home"] else ("away" if r.team_name == s["away"] else None)
            if side is None or pd.isna(r.value):
                continue
            if s["flip"]:
                side = "away" if side == "home" else "home"
            src = s["data_source"]
            vals.setdefault((r.stat_key, side), {}).setdefault(src, float(r.value))
            labels.setdefault(r.stat_key, r.stat_label or r.stat_key)
    rows = []
    for (key, side), by_src in vals.items():
        order = PRECEDENCE.get(key, DEFAULT)
        ranked = sorted(by_src, key=lambda s: order.index(s) if s in order else len(order))
        chosen = ranked[0]
        v = by_src[chosen]
        tol = TOLERANCE.get(key, 0.01)
        others = {s: by_src[s] for s in ranked[1:]}
        diverge = {s: x for s, x in others.items() if abs(x - v) > tol}
        rows.append({"estatística": labels.get(key, key), "time": meta.get("home_team_name") if side == "home"
                     else meta.get("away_team_name"), "fonte escolhida": chosen, "valor": v,
                     "outras fontes": ", ".join(f"{s} {x:g}" for s, x in others.items()) or "—",
                     "diverge": bool(diverge), "stat_key": key, "side": side})
    return pd.DataFrame(rows).sort_values(["diverge", "stat_key", "side"], ascending=[False, True, True]).reset_index(drop=True)


def record_divergences(db, match_id: int, table: Optional[pd.DataFrame] = None) -> int:
    """
    B7 — grava as divergências entre fontes (fonte primária, valor, valores das outras) em `source_divergences`.
    Nunca altera o número exibido: a fonte primária continua valendo e a divergência fica anotada.
    """
    tab = compare(db, match_id) if table is None else table
    if tab is None or tab.empty or not tab["diverge"].any():
        return 0
    d = tab[tab["diverge"]]
    with db.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS source_divergences (match_id INTEGER, stat_key TEXT, side TEXT, "
                     "fonte_primaria TEXT, valor REAL, outras TEXT, registrado_em TEXT DEFAULT (datetime('now')), "
                     "PRIMARY KEY (match_id, stat_key, side))")
        conn.executemany("INSERT OR REPLACE INTO source_divergences (match_id, stat_key, side, fonte_primaria, valor, outras) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         [(int(match_id), r["stat_key"], r["side"], r["fonte escolhida"], float(r["valor"]),
                           r["outras fontes"]) for r in d.to_dict("records")])
    return int(len(d))
