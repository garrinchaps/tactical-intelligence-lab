"""Leitura analítica de estatísticas agregadas (boxscore): pontos fortes e fracos com o método declarado."""

from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd

Fact = Tuple[str, str, str]


def box_facts(stats: pd.DataFrame, team: str, opp: str, goals_for: Optional[float],
              goals_against: Optional[float]) -> Tuple[List[Fact], List[Fact]]:
    """Leituras analíticas a partir das estatísticas agregadas. Devolve (fortes, fracos) como (texto, valor, método)."""
    def v(t, k):
        r = stats[(stats["team_name"] == t) & (stats["stat_key"] == k)]["value"]
        return float(r.iloc[0]) if not r.empty and pd.notna(r.iloc[0]) else None

    good, bad = [], []

    def cmp(k, label, higher=True, margin=0.25):
        a, o = v(team, k), v(opp, k)
        if a is None or o is None or (a + o) == 0:
            return
        rel = (a - o) / max(a, o)
        if abs(rel) < margin:
            return
        txt = f"{label}: {a:g} x {o:g}"
        ((good if (rel > 0) == higher else bad)).append((txt, f"{a:g} x {o:g}", "comparação direta com o adversário"))

    cmp("shots_total", "Volume de finalizações")
    cmp("shots_on_target", "Finalizações no alvo")
    cmp("corners", "Escanteios (pressão territorial)")
    cmp("possession_pct", "Posse de bola", margin=0.15)
    cmp("fouls", "Faltas cometidas", higher=False)
    cmp("yellow_cards", "Cartões amarelos", higher=False, margin=0.4)
    s_tot, s_on = v(team, "shots_total"), v(team, "shots_on_target")
    o_tot, o_on = v(opp, "shots_total"), v(opp, "shots_on_target")
    if s_tot and s_on is not None:
        acc = 100 * s_on / s_tot
        (good if acc >= 40 else bad if acc < 30 else []).append(
            (f"Precisão de finalização: {acc:.0f}% no alvo", f"{acc:.0f}%", "no alvo ÷ finalizações"))
    if s_on and goals_for is not None:
        conv = 100 * goals_for / s_on
        (good if conv >= 35 else bad if conv < 20 else []).append(
            (f"Eficiência: {goals_for:g} gol(s) em {s_on:g} no alvo ({conv:.0f}%)", f"{conv:.0f}%", "gols ÷ finalizações no alvo"))
    if o_on is not None and goals_against is not None and o_on > 0:
        saved = 100 * (o_on - goals_against) / o_on
        (good if saved >= 70 else bad if saved < 50 else []).append(
            (f"Defesa contra chutes no alvo: {saved:.0f}% não viraram gol", f"{saved:.0f}%", "(no alvo do rival − gols sofridos) ÷ no alvo do rival"))
    if o_tot is not None and s_tot is not None and o_tot >= 1.6 * max(s_tot, 1):
        bad.append((f"Cedeu muitas finalizações: {o_tot:g} do rival contra {s_tot:g}", f"{o_tot:g}", "finalizações sofridas"))
    return good, bad
