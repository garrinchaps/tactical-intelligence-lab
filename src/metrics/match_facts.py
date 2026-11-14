"""
Fatos da partida a partir dos eventos (StatsBomb / Wyscout convertido / simulado).

* goals(df)               → lista de gols: minuto, período, equipe, autor, tipo (pé, cabeça, pênalti, gol contra) e
                            assistência (último passe certo da equipe para o finalizador na mesma posse);
* shootout(df)            → placar da disputa de pênaltis, se houver;
* player_match_stats(df)  → uma linha por atleta com minutos estimados e as contagens usadas em scout;
* team_match_stats(df, t) → indicadores da equipe na partida (para comparar equipes e jogos).

Tudo é contagem direta de eventos; o que é estimado (minutos, assistência, PPDA) está dito no nome ou no texto.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

ON_TARGET = {"Goal", "Saved", "Saved To Post", "Saved to Post"}
BODY_PT = {"Head": "cabeça", "Left Foot": "pé esquerdo", "Right Foot": "pé direito", "Other": "outro"}

ON_BALL = {"Pass", "Carry", "Shot", "Dribble", "Ball Receipt*", "Miscontrol", "Dispossessed", "Clearance",
           "Interception", "Ball Recovery", "Goal Keeper", "Block", "Duel", "Foul Won", "50/50", "Shield"}
PLAYER_STAT_LABELS = {
    "minutos": "Minutos (estimados)", "toques": "Ações com a bola (toques)", "gols": "Gols", "assistencias": "Assistências", "finalizacoes": "Finalizações",
    "finalizacoes_no_alvo": "Finalizações no alvo", "xg": "xG", "passes": "Passes", "passes_certos": "Passes certos",
    "precisao_passe_pct": "Precisão de passe (%)", "passes_progressivos": "Passes progressivos",
    "quebras_de_linha": "Passes quebra-linhas", "passes_decisivos": "Passes para finalização", "cruzamentos": "Cruzamentos",
    "xt": "xT gerado", "dribles": "Dribles", "conducoes": "Conduções", "desarmes": "Desarmes", "interceptacoes": "Interceptações",
    "recuperacoes": "Recuperações", "pressoes": "Pressões", "acoes_defensivas": "Ações defensivas", "perdas_de_posse": "Perdas de posse",
    "faltas_cometidas": "Faltas cometidas", "faltas_sofridas": "Faltas sofridas", "cartoes_amarelos": "Cartões amarelos",
    "cartoes_vermelhos": "Cartões vermelhos",
}
TEAM_STAT_LABELS = {
    "gols": "Gols", "xg": "xG", "finalizacoes": "Finalizações", "finalizacoes_no_alvo": "Finalizações no alvo",
    "passes": "Passes", "precisao_passe_pct": "Precisão de passe (%)", "share_passes_pct": "Posse (% dos passes)",
    "field_tilt_pct": "Field tilt (%)", "ppda": "PPDA (estimado)", "passes_progressivos": "Passes progressivos",
    "entradas_na_area": "Entradas na área", "cruzamentos": "Cruzamentos", "escanteios": "Escanteios",
    "recuperacoes": "Recuperações", "perdas_de_posse": "Perdas de posse", "xt": "xT gerado", "faltas": "Faltas",
    "cartoes_amarelos": "Cartões amarelos", "cartoes_vermelhos": "Cartões vermelhos",
}


def _col(df: pd.DataFrame, name: str, default: Any = None) -> pd.Series:
    return df[name] if name in df.columns else pd.Series(default, index=df.index)


def _regular(df: pd.DataFrame) -> pd.DataFrame:
    """Sem a disputa de pênaltis (período 5)."""
    return df[_col(df, "period", 1) <= 4]


# ---------------------------------------------------------------------------- gols
def goals(df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    d = _regular(df).sort_values(["period", "minute", "second"] if "second" in df.columns else ["period", "minute"])
    teams = d["team_name"].dropna().unique().tolist()
    out: List[Dict[str, Any]] = []
    shots = d[(d["type_name"] == "Shot") & (_col(d, "shot_outcome_name") == "Goal")]
    passes = d[(d["type_name"] == "Pass") & (_col(d, "pass_outcome_name").isna())]
    for s in shots.itertuples():
        kind = "pênalti" if getattr(s, "shot_type_name", None) == "Penalty" else \
            BODY_PT.get(getattr(s, "shot_body_part_name", None), "")
        assist = None
        if kind != "pênalti" and "pass_recipient_name" in d.columns:
            cand = passes[(passes["team_name"] == s.team_name) & (passes["pass_recipient_name"] == s.player_name) &
                          (passes.index < s.Index)]
            if "possession" in d.columns and pd.notna(getattr(s, "possession", None)):
                cand = cand[cand["possession"] == s.possession]
            if not cand.empty:
                assist = str(cand.iloc[-1]["player_name"])
        out.append({"periodo": int(s.period), "minuto": int(s.minute) + 1, "equipe": s.team_name, "jogador": s.player_name,
                    "tipo": kind, "assistencia": assist, "gol_contra": False})
    for r in d[d["type_name"] == "Own Goal Against"].itertuples():
        beneficiary = next((t for t in teams if t != r.team_name), r.team_name)
        out.append({"periodo": int(r.period), "minuto": int(r.minute) + 1, "equipe": beneficiary,
                    "jogador": r.player_name, "tipo": "gol contra", "assistencia": None, "gol_contra": True})
    return sorted(out, key=lambda g: (g["periodo"], g["minuto"]))


def goal_line(g: Dict[str, Any]) -> str:
    """Ex.: "23' Lionel Messi (pênalti)" / "81' Kylian Mbappé (pé direito, assist. Marcus Thuram)"."""
    det = [g["tipo"]] if g["tipo"] else []
    if g.get("assistencia"):
        det.append(f"assist. {g['assistencia']}")
    return f"{g['minuto']}' {g['jogador']}" + (f" ({', '.join(det)})" if det else "")


def shootout(df: Optional[pd.DataFrame]) -> Optional[Dict[str, int]]:
    if df is None or df.empty or "period" not in df.columns:
        return None
    p = df[(df["period"] == 5) & (df["type_name"] == "Shot")]
    if p.empty:
        return None
    return {t: int(((p["team_name"] == t) & (_col(p, "shot_outcome_name") == "Goal")).sum())
            for t in df["team_name"].dropna().unique()}


# --------------------------------------------------------------------- atletas
def _minutes(df: pd.DataFrame) -> Dict[str, float]:
    """Minutos estimados: entrada/saída pelas substituições; demais, do início ao fim da partida."""
    d = _regular(df)
    end = float(d["minute"].max() + 1) if not d.empty else 90.0
    mins: Dict[str, List[float]] = {}
    for p in d["player_name"].dropna().unique():
        mins[str(p)] = [0.0, end]
    subs = d[d["type_name"] == "Substitution"]
    for s in subs.itertuples():
        out_p = str(s.player_name)
        if out_p in mins:
            mins[out_p][1] = float(s.minute)
        inn = getattr(s, "substitution_replacement_name", None)
        if isinstance(inn, str) and inn:
            mins.setdefault(inn, [0.0, end])[0] = float(s.minute)
    red = d[_col(d, "foul_committed_card_name").isin(["Red Card", "Second Yellow"])]
    for r in red.itertuples():
        if str(r.player_name) in mins:
            mins[str(r.player_name)][1] = min(mins[str(r.player_name)][1], float(r.minute))
    return {p: round(max(b - a, 0.0), 0) for p, (a, b) in mins.items()}


def player_match_stats(df: Optional[pd.DataFrame], team: Optional[str] = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    d = _regular(df)
    d = d[d["player_name"].notna()]
    if team:
        d = d[d["team_name"] == team]
    if d.empty:
        return pd.DataFrame()
    g = goals(df)
    mins = _minutes(df)
    t = d["type_name"]
    is_pass = t == "Pass"
    ok_pass = is_pass & _col(d, "pass_outcome_name").isna()
    shot = t == "Shot"
    card = _col(d, "foul_committed_card_name")
    f = pd.DataFrame({
        "jogador": d["player_name"], "equipe": d["team_name"], "posicao": _col(d, "position_name", ""),
        "toques": t.isin(ON_BALL).astype(int),
        "passes": is_pass.astype(int), "passes_certos": ok_pass.astype(int),
        "passes_progressivos": (ok_pass & (_col(d, "is_progressive_action", 0) == 1)).astype(int),
        "quebras_de_linha": (ok_pass & (_col(d, "is_line_breaking_pass", 0) == 1)).astype(int),
        "cruzamentos": (is_pass & (_col(d, "is_pass_cross", 0).fillna(0).astype(bool))).astype(int),
        "finalizacoes": shot.astype(int),
        "finalizacoes_no_alvo": (shot & _col(d, "shot_outcome_name").isin(ON_TARGET)).astype(int),
        "xg": np.where(shot, pd.to_numeric(_col(d, "shot_statsbomb_xg", 0), errors="coerce").fillna(0), 0.0),
        "xt": pd.to_numeric(_col(d, "delta_xt", 0), errors="coerce").fillna(0).clip(lower=0),
        "dribles": (t == "Dribble").astype(int), "conducoes": (t == "Carry").astype(int),
        "desarmes": ((t == "Duel") & (_col(d, "duel_type_name") == "Tackle")).astype(int),
        "interceptacoes": (t == "Interception").astype(int), "recuperacoes": (t == "Ball Recovery").astype(int),
        "pressoes": (t == "Pressure").astype(int),
        "acoes_defensivas": (_col(d, "is_defensive_action", 0).fillna(0) == 1).astype(int),
        "perdas_de_posse": (_col(d, "is_turnover", 0).fillna(0) == 1).astype(int),
        "faltas_cometidas": (t == "Foul Committed").astype(int), "faltas_sofridas": (t == "Foul Won").astype(int),
        "cartoes_amarelos": (card == "Yellow Card").astype(int),
        "cartoes_vermelhos": card.isin(["Red Card", "Second Yellow"]).astype(int),
    })
    # passes que antecedem finalização (último passe certo para o finalizador na posse)
    key = []
    if "pass_recipient_name" in d.columns:
        passes = d[ok_pass]
        for s in d[shot].itertuples():
            c = passes[(passes["team_name"] == s.team_name) & (passes["pass_recipient_name"] == s.player_name) &
                       (passes.index < s.Index)]
            if "possession" in d.columns:
                c = c[c["possession"] == s.possession]
            if not c.empty:
                key.append(str(c.iloc[-1]["player_name"]))
    agg = f.groupby(["jogador", "equipe"], as_index=False).agg(
        {**{c: "sum" for c in f.columns if c not in ("jogador", "equipe", "posicao")},
         "posicao": lambda s: s.dropna().mode().iloc[0] if not s.dropna().empty else ""})
    agg["gols"] = agg["jogador"].map(lambda p: sum(1 for x in g if x["jogador"] == p and not x["gol_contra"]))
    agg["assistencias"] = agg["jogador"].map(lambda p: sum(1 for x in g if x.get("assistencia") == p))
    agg["passes_decisivos"] = agg["jogador"].map(lambda p: key.count(p))
    agg["minutos"] = agg["jogador"].map(lambda p: mins.get(p, 0.0))
    agg["precisao_passe_pct"] = np.where(agg["passes"] > 0, (100 * agg["passes_certos"] / agg["passes"].clip(lower=1)).round(1), np.nan)
    agg["xg"] = agg["xg"].round(2)
    agg["xt"] = agg["xt"].round(3)
    cols = ["jogador", "equipe", "posicao"] + [c for c in PLAYER_STAT_LABELS if c in agg.columns]
    return agg[cols].sort_values(["equipe", "minutos"], ascending=[True, False]).reset_index(drop=True)


def per90(stats: pd.DataFrame) -> pd.DataFrame:
    """Converte contagens em valores por 90 minutos (percentuais e minutos ficam como estão)."""
    out = stats.copy()
    m = out["minutos"].clip(lower=1)
    for c in PLAYER_STAT_LABELS:
        if c in out.columns and c not in ("minutos", "precisao_passe_pct"):
            out[c] = (out[c] * 90 / m).round(2)
    return out


# --------------------------------------------------------------------- equipes
def team_match_stats(df: Optional[pd.DataFrame], team: str) -> Dict[str, Any]:
    if df is None or df.empty:
        return {}
    d = _regular(df)
    own, opp = d[d["team_name"] == team], d[d["team_name"] != team]
    t = own["type_name"]
    p_all = d[d["type_name"] == "Pass"]
    p_own = own[t == "Pass"]
    ok = p_own[_col(p_own, "pass_outcome_name").isna()]
    f3 = p_all[p_all["x"] >= 80]
    shots = own[t == "Shot"]
    opp_build = opp[(opp["type_name"] == "Pass") & (opp["x"] < 72)]
    high_def = own[(_col(own, "is_defensive_action", 0).fillna(0) == 1) & (own["x"] >= 48) & (own["type_name"] != "Pressure")]
    card = _col(own, "foul_committed_card_name")
    g = goals(df)
    return {
        "gols": sum(1 for x in g if x["equipe"] == team),
        "xg": round(float(pd.to_numeric(_col(shots, "shot_statsbomb_xg", 0), errors="coerce").fillna(0).sum()), 2),
        "finalizacoes": int(len(shots)),
        "finalizacoes_no_alvo": int(_col(shots, "shot_outcome_name").isin(ON_TARGET).sum()),
        "passes": int(len(p_own)),
        "precisao_passe_pct": round(100 * len(ok) / len(p_own), 1) if len(p_own) else None,
        "share_passes_pct": round(100 * len(p_own) / len(p_all), 1) if len(p_all) else None,
        "field_tilt_pct": round(float(100 * (f3["team_name"] == team).sum() / len(f3)), 1) if len(f3) else None,
        "ppda": round(len(opp_build) / len(high_def), 2) if len(high_def) else None,
        "passes_progressivos": int((_col(ok, "is_progressive_action", 0) == 1).sum()),
        "entradas_na_area": int((_col(own, "is_box_entry", 0).fillna(0) == 1).sum()),
        "cruzamentos": int(_col(p_own, "is_pass_cross", 0).fillna(0).astype(bool).sum()),
        "escanteios": int((_col(p_own, "pass_type_name") == "Corner").sum()),
        "recuperacoes": int((t == "Ball Recovery").sum()),
        "perdas_de_posse": int((_col(own, "is_turnover", 0).fillna(0) == 1).sum()),
        "xt": round(float(pd.to_numeric(_col(own, "delta_xt", 0), errors="coerce").fillna(0).clip(lower=0).sum()), 2),
        "faltas": int((t == "Foul Committed").sum()),
        "cartoes_amarelos": int((card == "Yellow Card").sum()),
        "cartoes_vermelhos": int(card.isin(["Red Card", "Second Yellow"]).sum()),
    }
