"""
Resposta DIRETA da IA do laboratório (rodada 11).

Antes, a IA juntava "os números mais fora da curva" embaixo de qualquer resposta — dados certos, mas sem relação com a
pergunta. Agora ela primeiro entende QUAL número foi perguntado e de QUEM (jogador ou time). Achou o número e ele existe
neste jogo → responde em uma linha e mostra o ranking que embasa. Não achou, ou o jogo não mede → não inventa: devolve
None e o app mostra só a resposta do analista (ou diz que não tem o dado).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# métrica → (rótulo, palavras que a pergunta usa; TODAS as de um grupo precisam aparecer)
METRICS: Dict[str, Tuple[str, List[Tuple[str, ...]]]] = {
    "off_target": ("finalizações para fora", [("chut", "fora"), ("finaliz", "fora"), ("errou", "chute"), ("errou", "gol")]),
    "on_target": ("finalizações no alvo", [("chut", "alvo"), ("chut", "gol", "certo"), ("no alvo",), ("melhor", "chut"),
                                            ("chut", "melhor"), ("finaliz", "certa")]),
    "blocked": ("finalizações bloqueadas", [("bloquead",)]),
    "shots": ("finalizações", [("chut",), ("finaliz",), ("arremat",)]),
    "xg": ("xG (qualidade das chances)", [("xg",), ("chance", "clara"), ("mais perigo",), ("criou perigo",)]),
    "goals": ("gols", [("gol",)]),
    "final_third": ("passes para o terço final", [("terc", "final"), ("ultimo terco",)]),
    "box_passes": ("passes para dentro da área", [("passe", "area"), ("passes", "area")]),
    "progressive": ("passes progressivos", [("progress",), ("passe", "vertical")]),
    "crosses": ("cruzamentos", [("cruzam",), ("cruzou",)]),
    "passes_ok": ("passes certos", [("passe", "cert"), ("acert", "passe")]),
    "passes": ("passes", [("passe",), ("tocou", "bola")]),
    "dribbles": ("dribles tentados", [("drible",), ("driblou",)]),
    "dribbled_past": ("vezes driblado", [("driblado",), ("foi driblado",)]),
    "tackles": ("desarmes", [("desarm",)]),
    "interceptions": ("interceptações", [("intercept",)]),
    "recoveries": ("recuperações de bola", [("recuper",), ("roubou", "bola"), ("roubadas",)]),
    "pressures": ("pressões no portador", [("press",)]),
    "losses": ("perdas de posse", [("perd", "bola"), ("perd", "posse"), ("perdeu", "mais")]),
    "fouls": ("faltas cometidas", [("falta", "comet"), ("mais falta",), ("faltoso",)]),
    "fouled": ("faltas sofridas", [("falta", "sofr"), ("sofreu", "falta")]),
    "aerials_lost": ("duelos aéreos perdidos", [("aere", "perd"), ("cabec", "perd")]),
    "aerials_won": ("duelos aéreos ganhos", [("aere",), ("cabec",), ("jogo aereo",)]),
    "chances_created": ("chances criadas", [("chance", "criad"), ("criou", "chance"), ("assistencia",), ("assistiu",)]),
}
TEAM_ONLY = {"possession_pct": ("posse de bola (%)", [("posse",)]), "corners": ("escanteios", [("escanteio",)])}
FOTMOB_KEYS = {"shots": "totalShots", "on_target": "shotsOnTarget", "xg": "xg", "goals": "totalGoals", "passes_ok":
               "accurate_passes", "passes": "accurate_passes_total", "final_third": "passes_into_final_third",
               "dribbles": "dribbles_succeeded_total", "dribbled_past": "dribbled_past", "tackles": "matchstats.headers.tackles",
               "interceptions": "interceptions", "recoveries": "recoveries", "losses": "dispossessed", "fouls": "foulsCommitted",
               "fouled": "was_fouled", "crosses": "accurate_crosses", "chances_created": "chances_created", "blocked": "shot_blocks",
               "aerials_won": "aerials_won"}
FACT_KEY = {"shots": "shots_total", "on_target": "shots_on_target", "off_target": "shots_off_target", "xg": "xg",
            "passes": "passes_total", "passes_ok": "passes_accurate", "crosses": "crosses_total", "tackles": "tackles_won",
            "interceptions": "interceptions", "fouls": "fouls", "aerials_won": "aerials_won", "blocked": "shots_blocked",
            "possession_pct": "possession_pct", "corners": "corners", "dribbles": "dribbles_completed"}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def detect(question: str) -> Optional[str]:
    q = " " + re.sub(r"[^a-z0-9 ]", " ", _fold(question)) + " "
    for key, (_, groups) in {**METRICS, **TEAM_ONLY}.items():
        for g in groups:
            if all(w in q for w in g):
                return key
    return None


def wants_player(question: str) -> bool:
    q = _fold(question)
    return bool(re.search(r"\bquem\b|\bqual jogador\b|\bjogador\b|\batleta\b", q)) and not re.search(r"qual time|que time|qual equipe", q)


def player_table_events(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["player_name"].notna() & (df["period"].fillna(1) <= 4)]
    rows = []
    for (team, pl), g in d.groupby(["team_name", "player_name"]):
        sh = g[g["type_name"] == "Shot"]
        out = sh["shot_outcome_name"].astype(str)
        p = g[g["type_name"] == "Pass"]
        ok = p["pass_outcome_name"].isna()
        x0, x1 = p["x"].astype(float), pd.to_numeric(p["end_x"], errors="coerce")
        d0 = np.hypot(120 - x0, 40 - p["y"].astype(float))
        d1 = np.hypot(120 - x1.fillna(x0), 40 - pd.to_numeric(p["end_y"], errors="coerce").fillna(p["y"]))
        rows.append({"team": team, "player": pl, "shots": len(sh),
                     "on_target": int(out.isin(["Goal", "Saved", "Saved To Post"]).sum()),
                     "off_target": int(out.isin(["Off T", "Wayward", "Post", "Saved Off T"]).sum()),
                     "blocked": int((out == "Blocked").sum()), "goals": int((out == "Goal").sum()),
                     "xg": round(float(pd.to_numeric(sh["shot_statsbomb_xg"], errors="coerce").fillna(0).sum()), 2),
                     "passes": len(p), "passes_ok": int(ok.sum()),
                     "final_third": int((ok & (x0 < 80) & (x1 >= 80)).sum()),
                     "box_passes": int((ok & (x1 >= 102) & pd.to_numeric(p["end_y"], errors="coerce").between(18, 62)).sum()),
                     "progressive": int((ok & ((d0 - d1) >= np.maximum(10, 0.25 * d0)) & (x1 >= 60)).sum()),
                     "crosses": int(p["is_pass_cross"].fillna(False).astype(bool).sum()) if "is_pass_cross" in p else None,
                     "dribbles": int((g["type_name"] == "Dribble").sum()),
                     "dribbled_past": int((g["type_name"] == "Dribbled Past").sum()),
                     "tackles": int(((g["type_name"] == "Duel") & (g["duel_type_name"] == "Tackle")).sum()),
                     "interceptions": int((g["type_name"] == "Interception").sum()),
                     "recoveries": int((g["type_name"] == "Ball Recovery").sum()),
                     "pressures": int((g["type_name"] == "Pressure").sum()),
                     "losses": int(g["type_name"].isin(["Dispossessed", "Miscontrol"]).sum()),
                     "fouls": int((g["type_name"] == "Foul Committed").sum()),
                     "fouled": int((g["type_name"] == "Foul Won").sum()),
                     "aerials_lost": int(((g["type_name"] == "Duel") & (g["duel_type_name"] == "Aerial Lost")).sum())})
    return pd.DataFrame(rows)


def player_table_box(box: Dict[str, Any]) -> pd.DataFrame:
    ps = (box or {}).get("player_stats")
    if ps is None or getattr(ps, "empty", True) or "stats" not in ps:
        return pd.DataFrame()
    rows = []
    for r in ps.itertuples():
        s = r.stats if isinstance(r.stats, dict) else {}
        row = {"team": r.team_name, "player": r.player_name}
        for k, fk in FOTMOB_KEYS.items():
            v = s.get(fk)
            try:
                row[k] = float(v) if v is not None else None
            except (TypeError, ValueError):
                row[k] = None
        if row.get("shots") is not None and row.get("on_target") is not None and s.get("blockedShots") is not None:
            row["off_target"] = max(0.0, row["shots"] - row["on_target"] - float(s.get("blockedShots") or 0))
        rows.append(row)
    return pd.DataFrame(rows)


def _n(v) -> str:
    v = float(v)
    if v.is_integer():
        return f"{int(v)}"
    return f"{v:.1f}" if abs(v) >= 10 else f"{v:.2f}"


def answer(question: str, meta: Dict[str, Any], df: Optional[pd.DataFrame], box: Optional[Dict[str, Any]],
           team_facts: Optional[list] = None, pt=lambda x: x) -> Optional[Dict[str, Any]]:
    key = detect(question)
    if key is None:
        return None
    label = {**METRICS, **TEAM_ONLY}[key][0]
    has_events = df is not None and not getattr(df, "empty", True)
    table = player_table_events(df) if has_events else player_table_box(box)
    source = "lances do jogo" if has_events else f"números por jogador ({meta.get('data_source') or 'fonte'})"
    if wants_player(question) and key in METRICS:
        if table.empty or key not in table or table[key].dropna().empty:
            return {"markdown": f"Não tenho **{label}** por jogador neste jogo — a fonte não traz esse número. "
                                f"Nada a responder sem inventar.", "key": key, "kind": "sem_dado"}
        t = table.dropna(subset=[key]).sort_values(key, ascending=False)
        t = t[t[key] > 0]
        if t.empty:
            return {"markdown": f"Ninguém registrou **{label}** neste jogo (zero para todos os jogadores com números).",
                    "key": key, "kind": "zero"}
        top = t.iloc[0]
        tie = t[t[key] == top[key]]
        lead = (f"**{top['player']}** ({pt(top['team'])}), com {_n(top[key])}" if len(tie) == 1 else
                "empate entre " + ", ".join(f"**{r.player}** ({pt(r.team)})" for r in tie.itertuples()) + f", com {_n(top[key])}")
        rank = "\n".join(f"{i}. {r.player} ({pt(r.team)}) — {_n(getattr(r, key))}" for i, r in
                         enumerate(t.head(5).itertuples(), 1))
        by_team = t.groupby("team")[key].sum()
        md = (f"Quem teve mais {label}: {lead}.\n\n**Os números que embasam** (top 5):\n\n{rank}\n\n"
              f"Total por time: " + " · ".join(f"{pt(k)} {_n(v)}" for k, v in by_team.items()) + f".\n\n_Fonte: {source}._")
        return {"markdown": md, "key": key, "kind": "jogador"}
    # pergunta do time
    teams = [t for t in (meta.get("home_team_name"), meta.get("away_team_name")) if t]
    vals: Dict[str, float] = {}
    if key in METRICS and not table.empty and key in table and table[key].notna().any():
        vals = table.groupby("team")[key].sum().to_dict()
    else:
        if team_facts is None:
            try:
                from src.intelligence.lab_ai.facts import match_facts

                team_facts = match_facts(meta, df, box)
            except Exception:
                team_facts = []
        fk = FACT_KEY.get(key, key)
        for f in team_facts or []:
            if getattr(f, "key", None) == fk and not getattr(f, "player", None):
                vals[f.team] = f.value
    if not vals:
        return {"markdown": f"Não tenho **{label}** neste jogo — a fonte não mede esse número.", "key": key, "kind": "sem_dado"}
    items = sorted(vals.items(), key=lambda kv: -kv[1])
    lead = items[0]
    pct = "%" if key == "possession_pct" else ""
    label_t = label.replace(" (%)", "")
    note = (" Com lances, a posse é estimada pela fatia de passes de cada time." if key == "possession_pct" and has_events
            else "")
    md = (f"**{pt(lead[0])}** teve mais {label_t}: {_n(lead[1])}{pct}" +
          (f" contra {_n(items[1][1])}{pct} de {pt(items[1][0])}." if len(items) > 1 else ".") + note +
          f"\n\n_Fonte: {source if key not in TEAM_ONLY else 'estatísticas do jogo'}._")
    return {"markdown": md, "key": key, "kind": "time"}
