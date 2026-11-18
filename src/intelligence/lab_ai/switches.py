"""
Reação às inversões de jogo (só jogos com lances e coordenadas).

Inversão = passe certo que troca o corredor (marcado como "switch" pela fonte ou com deslocamento lateral ≥ 35 jardas).
Depois de cada inversão, olhamos os 8 segundos seguintes da mesma posse:
  * quem do time que defende fez a 1ª ação sobre a bola (pressão, duelo, desarme, interceptação, falta, bloqueio, corte)
    e quanto tempo levou;
  * o que o ataque conseguiu: chegar ao último terço, entrar na área, finalizar.
Por defensor: quantas vezes chegou primeiro, tempo médio, e quanto o ataque avançou quando ELE foi o primeiro × quando
ninguém chegou em 5 s. Isto mede REAÇÃO NA BOLA pelos eventos; postura corporal e posicionamento sem a bola exigem
vídeo ou tracking, que as fontes abertas não têm.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

DEF_TYPES = {"Pressure", "Duel", "Interception", "Foul Committed", "Block", "Clearance", "Ball Recovery"}
WINDOW_S, LATE_S = 8.0, 5.0


def _side(y: float) -> str:
    # StatsBomb: ataque para a direita, y = 0 é o lado ESQUERDO de quem ataca
    return "esquerdo" if y < 80 / 3 else ("direito" if y > 160 / 3 else "central")


def switch_events(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    d = df[df["period"].fillna(1) <= 4].sort_values(["period", "index_num"]).reset_index(drop=True)
    d["t"] = d["minute"].fillna(0) * 60 + d["second"].fillna(0)
    is_pass = (d["type_name"] == "Pass") & d["pass_outcome_name"].isna()
    flag = d["is_pass_Switch"].fillna(False).astype(bool) if "is_pass_Switch" in d else False
    lat = (pd.to_numeric(d["end_y"], errors="coerce") - pd.to_numeric(d["y"], errors="coerce")).abs()
    idx = d.index[is_pass & (flag | (lat >= 35))].tolist()
    out = []
    for i in idx:
        r = d.loc[i]
        team, per, t0, poss = r["team_name"], r["period"], r["t"], r["possession"]
        nxt = d[(d.index > i) & (d["period"] == per) & (d["t"] <= t0 + WINDOW_S) & (d["possession"] == poss)]
        own = nxt[nxt["team_name"] == team]
        opp = nxt[(nxt["team_name"] != team) & nxt["type_name"].isin(DEF_TYPES)]
        first = opp.iloc[0] if len(opp) else None
        out.append({
            "team": team, "minute": int(r["minute"] or 0), "passer": r["player_name"], "receiver": r.get("pass_recipient_name"),
            "side": _side(float(r["end_y"])) if pd.notna(r["end_y"]) else "—",
            "reactor": first["player_name"] if first is not None else None,
            "reactor_pos": first["position_name"] if first is not None else None,
            "reaction_s": float(first["t"] - t0) if first is not None else None,
            "final_third": bool((own["x"] >= 80).any() or (pd.notna(r["end_x"]) and r["end_x"] >= 80)),
            "box": bool(((own["x"] >= 102) & own["y"].between(18, 62)).any()),
            "shot": bool((own["type_name"] == "Shot").any()),
        })
    return out


def reaction_table(sw: List[Dict[str, Any]], defending: str) -> pd.DataFrame:
    """Uma linha por defensor do time `defending`: como reagiu às inversões do adversário."""
    s = pd.DataFrame([x for x in sw if x["team"] != defending])
    if s.empty:
        return pd.DataFrame()
    late_mask = s["reaction_s"].isna() | (s["reaction_s"] > LATE_S)
    late_adv = float(s.loc[late_mask, "final_third"].mean()) if late_mask.any() else np.nan
    rows = []
    for pl, g in s.dropna(subset=["reactor"]).groupby("reactor"):
        rows.append({"jogador": pl, "posição": g["reactor_pos"].mode().iloc[0] if g["reactor_pos"].notna().any() else "",
                     "chegou primeiro": len(g), "tempo médio (s)": round(float(g["reaction_s"].mean()), 1),
                     "ataque chegou ao último terço (%)": round(100 * float(g["final_third"].mean()), 0),
                     "terminou em chute (%)": round(100 * float(g["shot"].mean()), 0),
                     "lado": g["side"].mode().iloc[0]})
    out = pd.DataFrame(rows).sort_values("chegou primeiro", ascending=False) if rows else pd.DataFrame()
    out.attrs.update(total=len(s), sem_reacao=int(late_mask.sum()),
                     avanco_sem_reacao=None if np.isnan(late_adv) else round(100 * late_adv, 0),
                     por_lado=s.groupby("side")["final_third"].agg(["size", "mean"]).round(2).to_dict("index"))
    return out


def switch_facts(df: pd.DataFrame, home: str, away: str) -> List[Any]:
    from src.intelligence.lab_ai.facts import Fact

    sw = switch_events(df)
    facts = []
    for defending, attacker in ((home, away), (away, home)):
        tab = reaction_table(sw, defending)
        tot = tab.attrs.get("total", 0) if hasattr(tab, "attrs") else 0
        if not tot:
            continue
        sem = tab.attrs.get("sem_reacao", 0)
        lados = tab.attrs.get("por_lado", {})
        worst = max(lados.items(), key=lambda kv: (kv[1]["mean"], kv[1]["size"]))[0] if lados else None
        slow = tab[(tab["chegou primeiro"] >= 2)].sort_values("tempo médio (s)", ascending=False).head(1) if not tab.empty else tab
        facts.append(Fact("sw:reacao", "reação às inversões", "padrão", defending, attacker, float(sem),
                          opp_value=None, sense=0, keywords="invers lado virada troca reage reação reagir",
                          origin="lances do jogo (inversões)",
                          extra={"total": tot, "sem_reacao": sem, "avanco_sem_reacao": tab.attrs.get("avanco_sem_reacao"),
                                 "lado_mais_fragil": worst, "por_lado": lados,
                                 "mais_lento": slow.iloc[0].to_dict() if len(slow) else None,
                                 "tabela": tab.head(8).to_dict("records") if not tab.empty else []}))
    return facts
