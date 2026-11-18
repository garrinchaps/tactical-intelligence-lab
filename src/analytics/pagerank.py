"""
Rodada 13 — PageRank aplicado ao futebol (o mesmo algoritmo do Google, escrito em NumPy).

Força dos times: cada jogo é um "link" do perdedor para o vencedor (peso = 1 + saldo de gols; empate = meio voto para
cada lado). O PageRank distribui a "importância" pelos links: vencer quem vence muita gente vale mais do que vencer
quem só perde. Resultado: uma força de 0 a 100 que considera o NÍVEL de quem cada time enfrentou — coisa que a tabela
de pontos não faz. Fator de amortecimento d = 0,85 (o mesmo do artigo original).
"""

from __future__ import annotations

from typing import Dict, Sequence

import numpy as np
import pandas as pd


def pagerank(nodes: Sequence[str], edges: Sequence[tuple], d: float = 0.85, iters: int = 100, tol: float = 1e-10
             ) -> Dict[str, float]:
    """edges = (de, para, peso). Iteração de potência com nós "sem saída" redistribuídos igualmente."""
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    if n == 0:
        return {}
    W = np.zeros((n, n))
    for a, b, w in edges:
        if a in idx and b in idx and w > 0:            # a == b: laço (time que vence segura parte da importância)
            W[idx[b], idx[a]] += w                       # coluna = de onde sai o voto
    out = W.sum(axis=0)
    dangling = out == 0
    M = np.divide(W, out, out=np.zeros_like(W), where=out > 0)
    r = np.full(n, 1.0 / n)
    for _ in range(iters):
        new = (1 - d) / n + d * (M @ r + r[dangling].sum() / n)
        if np.abs(new - r).sum() < tol:
            r = new
            break
        r = new
    return {node: float(r[i]) for node, i in idx.items()}


def team_strength(matches: pd.DataFrame) -> pd.DataFrame:
    """matches: home_team_name, away_team_name, home_score, away_score. Devolve força 0–100 + jogos e pontos."""
    m = matches.dropna(subset=["home_score", "away_score"])
    if m.empty:
        return pd.DataFrame()
    teams = sorted(set(m["home_team_name"]) | set(m["away_team_name"]))
    edges = []
    pts = {t: 0 for t in teams}
    games = {t: 0 for t in teams}
    for h, a, hs, as_ in zip(m["home_team_name"], m["away_team_name"], m["home_score"], m["away_score"]):
        hs, as_ = int(hs), int(as_)
        games[h] += 1
        games[a] += 1
        if hs > as_:
            edges.append((a, h, 1.0 + (hs - as_)))
            pts[h] += 3
        elif as_ > hs:
            edges.append((h, a, 1.0 + (as_ - hs)))
            pts[a] += 3
        else:
            edges += [(h, a, 0.5), (a, h, 0.5)]
            pts[h] += 1
            pts[a] += 1
    # quem vence "guarda" parte da importância (laço para si mesmo, peso = vitórias + meio empate): sem isso o único
    # empate de um time invicto mandaria TODA a importância dele para o adversário do empate
    edges += [(t, t, pts[t] / 3.0) for t in teams if pts[t] > 0]
    pr = pagerank(teams, edges)
    lo, hi = min(pr.values()), max(pr.values())
    rows = [{"time": t, "forca_pagerank": round(100 * (pr[t] - lo) / (hi - lo), 1) if hi > lo else 50.0,
             "jogos": games[t], "pontos": pts[t]} for t in teams]
    df = pd.DataFrame(rows).sort_values("forca_pagerank", ascending=False).reset_index(drop=True)
    df["posicao_pagerank"] = range(1, len(df) + 1)
    df["posicao_pontos"] = df["pontos"].rank(ascending=False, method="min").astype(int)
    return df
