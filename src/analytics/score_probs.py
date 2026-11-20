"""
Rodada 25b — probabilidades do jogo: placares (como o gráfico do Sofascore), vitória/empate/derrota e, em mata-mata,
classificação (ou título, se for final).

Como é calculado (estimativa, não certeza):
  * força de cada time nos últimos 20 jogos com estatísticas: gols esperados A FAVOR e CONTRA (xG da FotMob/ESPN;
    sem xG, os gols), 70% xG + 30% gols, puxada para a média com poucos jogos;
  * gols esperados do jogo: ataque de um × defesa do outro ÷ média, com vantagem de mando (+10% / −10%);
  * placares por Poisson com a correção de Dixon-Coles para 0×0, 1×0, 0×1 e 1×1 (empates baixos são mais comuns do que
    a Poisson simples diz);
  * mata-mata jogo único: empate vai para prorrogação (30 min = 1/3 dos gols esperados) e pênaltis (50%);
  * jogo de volta: soma o placar da ida (achado na base: mesmo confronto, mesma competição, até 70 dias antes);
  * final: classificação = título.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

MAX_GOALS = 7
RHO = -0.08          # correção de Dixon-Coles (valor típico da literatura)
HOME_ADV = 1.10
CUP_WORDS = ("copa", "cup", "pokal", "coupe", "coppa", "taça", "taca", "libertadores", "sudamericana", "sul-americana",
             "champions", "europa league", "conference", "recopa", "supercopa", "super cup", "fa cup", "efl", "trophy")


def _pois(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_matrix(lh: float, la: float, rho: float = RHO, n: int = MAX_GOALS) -> np.ndarray:
    """Matriz P[gols mandante, gols visitante] (0..n), normalizada para somar 1."""
    m = np.array([[_pois(lh, i) * _pois(la, j) for j in range(n + 1)] for i in range(n + 1)])
    tau = {(0, 0): 1 - lh * la * rho, (0, 1): 1 + lh * rho, (1, 0): 1 + la * rho, (1, 1): 1 - rho}
    for (i, j), t in tau.items():
        m[i, j] *= max(t, 0.0)
    return m / m.sum()


def outcome(m: np.ndarray) -> Dict[str, float]:
    home = float(np.tril(m, -1).sum())
    away = float(np.triu(m, 1).sum())
    return {"mandante": home, "empate": float(np.trace(m)), "visitante": away}


def team_strength(db, names: Sequence[str], n: int = 20, before: Optional[str] = None) -> Dict[str, Any]:
    from src.analytics import team_history as TH

    m = TH._matches(db, list(names), n=n, before=before)
    v = TH._vectors(db, m, list(names)) if not m.empty else pd.DataFrame()
    if v.empty:
        return {"jogos": 0}
    home = v["home_team_name"].isin(names)
    gf = pd.Series(np.where(home, v["home_score"], v["away_score"]), index=v.index).astype(float)
    ga = pd.Series(np.where(home, v["away_score"], v["home_score"]), index=v.index).astype(float)
    xf = pd.to_numeric(v.get("f_xg"), errors="coerce") if "f_xg" in v else pd.Series(np.nan, index=v.index)
    xa = pd.to_numeric(v.get("c_xg"), errors="coerce") if "c_xg" in v else pd.Series(np.nan, index=v.index)
    att = (.7 * xf.fillna(gf) + .3 * gf).mean()
    dfn = (.7 * xa.fillna(ga) + .3 * ga).mean()
    return {"jogos": int(len(v)), "ataque": float(att), "defesa": float(dfn), "com_xg": int(xf.notna().sum()),
            "competicoes": v["competition_name"].dropna().unique().tolist()}


def expected_goals(home: Dict[str, Any], away: Dict[str, Any], neutral: bool = False) -> Dict[str, float]:
    base = 1.35                                   # gols por time por jogo (média de futebol profissional)
    def shrink(x, n):
        w = min(1.0, (n or 0) / 12)
        return base + (x - base) * w if x == x else base
    ha, hd = shrink(home.get("ataque", base), home.get("jogos")), shrink(home.get("defesa", base), home.get("jogos"))
    aa, ad = shrink(away.get("ataque", base), away.get("jogos")), shrink(away.get("defesa", base), away.get("jogos"))
    adv = 1.0 if neutral else HOME_ADV
    lh = max(.15, ha * ad / base * adv)
    la = max(.15, aa * hd / base / adv)
    return {"mandante": round(lh, 2), "visitante": round(la, 2)}


def first_leg(db, home_names: Sequence[str], away_names: Sequence[str], competition: str, kickoff: str,
              days: int = 70) -> Optional[Dict[str, Any]]:
    """Jogo de ida: mesmo confronto (mando invertido), mesma competição, até `days` dias antes."""
    if not competition or not kickoff:
        return None
    since = (pd.to_datetime(kickoff[:10]) - pd.Timedelta(days=days)).date().isoformat()
    ph, pa = ",".join("?" * len(home_names)), ",".join("?" * len(away_names))
    try:
        with db.connect() as conn:
            r = pd.read_sql_query(
                f"SELECT match_date, home_team_name, away_team_name, home_score, away_score FROM matches "
                f"WHERE home_team_name IN ({pa}) AND away_team_name IN ({ph}) AND competition_name = ? "
                f"AND match_date >= ? AND match_date < ? AND home_score IS NOT NULL ORDER BY match_date DESC LIMIT 1",
                conn, params=[*away_names, *home_names, competition, since, kickoff[:10]])
    except Exception:
        return None
    if r.empty:
        return None
    x = r.iloc[0]
    # placar da ida do ponto de vista do mandante de HOJE (que foi visitante na ida)
    return {"data": str(x["match_date"])[:10], "gols_mandante_hoje": int(x["away_score"]),
            "gols_visitante_hoje": int(x["home_score"])}


def advance(m: np.ndarray, lh: float, la: float, agg_home: int = 0) -> Dict[str, float]:
    """Chance de cada lado passar: resultado do jogo + placar agregado; empate no agregado → prorrogação e pênaltis."""
    n = m.shape[0]
    p_home = p_away = p_tie = 0.0
    for i in range(n):
        for j in range(n):
            d = i - j + agg_home
            if d > 0:
                p_home += m[i, j]
            elif d < 0:
                p_away += m[i, j]
            else:
                p_tie += m[i, j]
    et = outcome(score_matrix(lh / 3, la / 3, rho=0.0, n=5))
    p_home += p_tie * (et["mandante"] + .5 * et["empate"])
    p_away += p_tie * (et["visitante"] + .5 * et["empate"])
    return {"mandante": p_home, "visitante": p_away, "prorrogacao_ou_penaltis": p_tie}


def guess_kind(db, home_names, away_names, competition: str, kickoff: str) -> str:
    if first_leg(db, home_names, away_names, competition, kickoff):
        return "volta"
    c = (competition or "").lower()
    return "unico" if any(w in c for w in CUP_WORDS) else "pontos"


def predict(db, home: str, away: str, home_names: Sequence[str], away_names: Sequence[str], competition: str = "",
            kickoff: str = "", kind: str = "auto", neutral: bool = False) -> Dict[str, Any]:
    """kind: 'pontos' (campeonato), 'unico' (mata-mata jogo único), 'volta' (jogo de volta), 'final'."""
    hs, as_ = team_strength(db, home_names), team_strength(db, away_names)
    if not hs.get("jogos") and not as_.get("jogos"):
        return {"ok": False, "motivo": "nenhum dos dois times tem jogos com estatísticas na base"}
    xg = expected_goals(hs, as_, neutral)
    m = score_matrix(xg["mandante"], xg["visitante"])
    res = outcome(m)
    flat = sorted(((float(m[i, j]), i, j) for i in range(m.shape[0]) for j in range(m.shape[1])), reverse=True)
    top = [{"placar": f"{i} x {j}", "prob": p} for p, i, j in flat[:8]]
    kind = guess_kind(db, home_names, away_names, competition, kickoff) if kind == "auto" else kind
    out = {"ok": True, "gols_esperados": xg, "resultado": res, "placares": top, "matriz": m.tolist(), "tipo": kind,
           "mais_provavel": top[0]["placar"], "over_2_5": float(sum(m[i, j] for i in range(m.shape[0])
                                                                    for j in range(m.shape[1]) if i + j >= 3)),
           "ambos_marcam": float(m[1:, 1:].sum()), "base": {home: hs, away: as_}}
    if kind in ("unico", "volta", "final"):
        leg = first_leg(db, home_names, away_names, competition, kickoff) if kind == "volta" else None
        agg = (leg["gols_mandante_hoje"] - leg["gols_visitante_hoje"]) if leg else 0
        out["ida"] = leg
        out["classificacao"] = advance(m, xg["mandante"], xg["visitante"], agg)
        out["titulo"] = kind == "final"
    return out
