"""
Dataset de perigo de posse (Camada A.1 e Camada B) — uma linha por AÇÃO com bola.

Pergunta: "no instante desta ação (passe ou condução), a posse vai terminar em finalização?"
Todas as variáveis usam apenas informação disponível NO INSTANTE da ação (sem vazamento):

  dist_to_goal_m      distância ao centro do gol adversário (m)
  angle_to_goal_deg   ângulo de visão entre as traves (graus)
  opp_density_5m      adversários num raio de 5 m — MEDIDO pelo StatsBomb 360 quando a partida
                      tem freeze frames; senão, proxy: eventos adversários a ≤ 5 m em ±5 s
                      (coluna density_source indica qual foi usado)
  passes_so_far       passes da equipe na posse antes desta ação
  zone_*              zona do campo (terço × faixa lateral, 9 categorias, one-hot)
  score_diff          saldo de gols da equipe antes da ação, limitado a [−2, 2]

Alvo: 1 se a mesma posse (mesmo id de posse e mesma equipe) tem uma finalização da equipe
nesta ação ou depois dela; 0 caso contrário. Grupo para validação: match_id (split por partida).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

YD_PER_M = 1 / 0.9144
RADIUS_YD = 5.0 * YD_PER_M
THIRDS = [("def", 0, 40), ("mid", 40, 80), ("att", 80, 121)]
LANES = [("esq", 0, 26.67), ("cen", 26.67, 53.33), ("dir", 53.33, 81)]
ZONE_COLS = [f"zone_{t}_{l}" for t, _, _ in THIRDS for l, _, _ in LANES]
FEATURES = ["dist_to_goal_m", "angle_to_goal_deg", "opp_density_5m", "passes_so_far", "score_diff"] + ZONE_COLS
BASELINE_FEATURES = ["dist_to_goal_m", "angle_to_goal_deg", "passes_so_far"]


def _zone_onehot(x: np.ndarray, y: np.ndarray) -> Dict[str, np.ndarray]:
    out = {}
    for t, x0, x1 in THIRDS:
        for l, y0, y1 in LANES:
            out[f"zone_{t}_{l}"] = ((x >= x0) & (x < x1) & (y >= y0) & (y < y1)).astype(int)
    return out


def opponents_from_360(frames: Optional[list]) -> Dict[str, np.ndarray]:
    """event_uuid → array (k, 2) com as posições dos adversários visíveis no freeze frame."""
    out: Dict[str, np.ndarray] = {}
    for fr in frames or []:
        opp = [p["location"] for p in fr.get("freeze_frame", []) if not p.get("teammate") and not p.get("actor")]
        out[fr["event_uuid"]] = np.array(opp, dtype=float).reshape(-1, 2)
    return out


def build_match_rows(df: pd.DataFrame, freeze: Optional[Dict[str, np.ndarray]] = None) -> pd.DataFrame:
    """`df` = eventos internos (formato do parser StatsBomb/Wyscout) de UMA partida."""
    d = df[(df["period"] <= 4)].copy()
    if d.empty:
        return pd.DataFrame()
    d = d.sort_values(["period", "index_num"], kind="stable").reset_index(drop=True)
    d["t"] = d["period"] * 10000 + d["minute"].fillna(0) * 60 + d["second"].fillna(0)

    # saldo de gols antes de cada evento (perspectiva de quem executa)
    teams = d["team_name"].dropna().unique().tolist()
    goals = {t: 0 for t in teams}
    diff = np.zeros(len(d))
    for i, r in enumerate(d.itertuples(index=False)):
        other = next((t for t in teams if t != r.team_name), None)
        diff[i] = goals.get(r.team_name, 0) - goals.get(other, 0)
        if r.type_name == "Shot" and getattr(r, "shot_outcome_name", None) == "Goal":
            goals[r.team_name] = goals.get(r.team_name, 0) + 1
        elif r.type_name == "Own Goal Against" and other:
            goals[other] = goals.get(other, 0) + 1
    d["score_diff"] = np.clip(diff, -2, 2)

    # passes da equipe na posse antes do evento + alvo (finalização da equipe na posse, desta ação em diante)
    d["passes_so_far"] = 0
    d["target"] = 0
    for _, g in d.groupby(["period", "possession"], sort=False):
        team = g["possession_team_name"].iloc[0]
        own = (g["team_name"] == team).to_numpy()
        is_pass = ((g["type_name"] == "Pass").to_numpy() & own).astype(int)
        d.loc[g.index, "passes_so_far"] = np.concatenate([[0], np.cumsum(is_pass)[:-1]])
        shot_own = ((g["type_name"] == "Shot").to_numpy() & own).astype(int)
        shot_from_here = np.cumsum(shot_own[::-1])[::-1] > 0
        d.loc[g.index, "target"] = shot_from_here.astype(int)

    act = d[d["type_name"].isin(["Pass", "Carry"]) & d["x"].notna() & d["y"].notna()
            & (d["team_name"] == d["possession_team_name"])].copy()
    if act.empty:
        return pd.DataFrame()
    x, y = act["x"].to_numpy(float), act["y"].to_numpy(float)
    dx = np.maximum(120.0 - x, 0.1)
    act["dist_to_goal_m"] = np.hypot(dx, 40.0 - y) * 0.9144
    act["angle_to_goal_deg"] = np.degrees(np.abs(np.arctan2(44.0 - y, dx) - np.arctan2(36.0 - y, dx)))

    dens = np.zeros(len(act))
    src = np.array(["proxy"] * len(act), dtype=object)
    opp_ev = d[d["x"].notna()][["team_name", "x", "y", "t"]]
    for k, r in enumerate(act.itertuples(index=False)):
        pts = freeze.get(str(r.event_id)) if freeze else None
        if pts is not None:
            dens[k] = int((np.hypot(pts[:, 0] - r.x, pts[:, 1] - r.y) <= RADIUS_YD).sum()) if len(pts) else 0
            src[k] = "statsbomb_360"
        else:
            o = opp_ev[(opp_ev["team_name"] != r.team_name) & (np.abs(opp_ev["t"] - r.t) <= 5)]
            # adversário registra no próprio referencial: espelha para o referencial de quem tem a bola
            ox, oy = 120.0 - o["x"].to_numpy(float), 80.0 - o["y"].to_numpy(float)
            dens[k] = int((np.hypot(ox - r.x, oy - r.y) <= RADIUS_YD).sum())
    act["opp_density_5m"] = dens
    act["density_source"] = src
    for col, vals in _zone_onehot(x, y).items():
        act[col] = vals
    keep = ["match_id", "team_name", "event_id", "minute", "density_source", "target"] + FEATURES
    return act[keep].reset_index(drop=True)


def build_dataset(match_ids: List[int], load_events, load_freeze=None, progress=None) -> pd.DataFrame:
    parts = []
    for i, mid in enumerate(match_ids):
        try:
            df = load_events(int(mid))
            fr = load_freeze(int(mid)) if load_freeze else None
            rows = build_match_rows(df, opponents_from_360(fr) if fr else None)
            if not rows.empty:
                parts.append(rows)
        except Exception as exc:
            if progress:
                progress(f"partida {mid} ignorada: {exc}")
        if progress and (i + 1) % 10 == 0:
            progress(f"{i + 1}/{len(match_ids)} partidas processadas")
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
