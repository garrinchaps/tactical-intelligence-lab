"""
Padrões de UMA partida com lances (rodada 5): bola parada, impacto das substituições e comportamento conforme o placar.

Regras honestas:
  * substituição: compara a janela ANTES e DEPOIS da troca (mesma duração, até 15 min), com o placar e as outras trocas
    simultâneas registrados — é associação no tempo, NÃO prova de que o jogador que entrou causou a mudança;
  * estado do jogo: minutos vencendo/empatando/perdendo e a produção por 15 min em cada estado; com poucos minutos num
    estado, o número é marcado como amostra pequena;
  * bola parada: só o que os lances registram (cobrador, altura, zona de chegada, primeiro contato, finalização em até
    15 s / 5 ações, segunda bola).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

SP_PATTERNS = {"From Corner": "escanteio", "From Free Kick": "falta", "From Throw In": "lateral"}


def _play(df: pd.DataFrame) -> pd.DataFrame:
    d = df[pd.to_numeric(df["period"], errors="coerce").fillna(1) < 5] if "period" in df else df
    cols = [c for c in ("period", "time_seconds", "index_num") if c in d]
    return d.sort_values(cols) if cols else d


def _abs_min(d: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(d["minute"], errors="coerce").fillna(0) + pd.to_numeric(d.get("second", 0), errors="coerce").fillna(0) / 60


def _zone(x: float, y: float) -> str:
    if x >= 114 and 30 <= y <= 50:
        return "pequena área"
    if x >= 102 and 18 <= y <= 62:
        return "primeiro pau" if y < 36 else ("segundo pau" if y > 44 else "marca do pênalti")
    if x >= 102:
        return "fora da área, na lateral"
    return "curto / fora da área"


# ------------------------------------------------------------------ bola parada
def set_pieces(df: pd.DataFrame, team: str) -> Dict[str, Any]:
    """Escanteios, faltas e laterais ofensivos de `team` e o que o rival fez nas mesmas situações (defesa)."""
    d = _play(df)
    out: Dict[str, Any] = {"equipe": team}
    for side, who in (("ataque", d["team_name"] == team), ("defesa", d["team_name"] != team)):
        res = {}
        for pat, name in SP_PATTERNS.items():
            seq = d[(d["play_pattern_name"] == pat) & who] if "play_pattern_name" in d else d.iloc[0:0]
            if seq.empty:
                continue
            first = seq[seq["type_name"] == "Pass"]
            first = first[first.get("pass_type_name", pd.Series(index=first.index, dtype=object)).isin(
                {"escanteio": ["Corner"], "falta": ["Free Kick"], "lateral": ["Throw-in"]}[name])]
            poss = seq["possession"].unique() if "possession" in seq else []
            shots = seq[seq["type_name"] == "Shot"]
            xg = float(pd.to_numeric(shots.get("shot_statsbomb_xg"), errors="coerce").fillna(0).sum())
            goals = int((shots.get("shot_outcome_name") == "Goal").sum())
            zones = first.apply(lambda r: _zone(float(r.get("end_x") or 0), float(r.get("end_y") or 0)), axis=1).value_counts() \
                if len(first) and "end_x" in first else pd.Series(dtype=int)
            # primeiro contato: quem recebeu a cobrança (passe certo) ou quem ganhou o duelo
            contact = first.loc[first["pass_outcome_name"].isna(), "pass_recipient_name"].value_counts() if len(first) else pd.Series(dtype=int)
            res[name] = {"cobrancas": int(len(first)), "posses": int(len(poss)), "finalizacoes": int(len(shots)),
                         "xg": round(xg, 2), "gols": goals,
                         "cobradores": {k: int(v) for k, v in first["player_name"].value_counts().head(3).items()},
                         "zonas": {k: int(v) for k, v in zones.head(4).items()},
                         "primeiro_contato_certo": int(contact.sum()) if len(contact) else 0,
                         "quem_recebe": {k: int(v) for k, v in contact.head(3).items()},
                         "altura": {k: int(v) for k, v in first.get("pass_height_name", pd.Series(dtype=object)).value_counts().items()}}
        out[side] = res
    # segunda bola: recuperação até 10 s depois de um escanteio/falta que foi afastado
    sec = 0
    for pat in ("From Corner", "From Free Kick"):
        seq = d[(d["play_pattern_name"] == pat) & (d["team_name"] == team)] if "play_pattern_name" in d else d.iloc[0:0]
        sec += int((seq["type_name"] == "Ball Recovery").sum())
    out["segundas_bolas_recuperadas"] = sec
    tot = sum(v["xg"] for v in out["ataque"].values())
    from src.intelligence.tactical_blocks import _shots, _xg

    all_xg = _xg(_shots(d, team))
    out["fatia_xg_bola_parada_pct"] = round(100 * tot / all_xg, 1) if all_xg else None
    return out


# ------------------------------------------------------------------ substituições
def _window_stats(d: pd.DataFrame, team: str, a: float, b: float) -> Dict[str, Any]:
    w = d[(d["_m"] >= a) & (d["_m"] < b)]
    mine, theirs = w[w["team_name"] == team], w[w["team_name"] != team]
    dur = max(b - a, 1e-6)
    p15 = lambda n: round(15 * n / dur, 2)
    passes_m = mine[mine["type_name"] == "Pass"]
    passes_t = theirs[theirs["type_name"] == "Pass"]
    tilt_m = int((pd.to_numeric(passes_m.get("x"), errors="coerce") >= 80).sum())
    tilt_t = int((pd.to_numeric(passes_t.get("x"), errors="coerce") >= 80).sum())
    xg = lambda s: float(pd.to_numeric(s.get("shot_statsbomb_xg"), errors="coerce").fillna(0).sum())
    sh_m, sh_t = mine[mine["type_name"] == "Shot"], theirs[theirs["type_name"] == "Shot"]
    return {"minutos": round(dur, 1), "passes_15": p15(len(passes_m)),
            "posse_pct": round(100 * len(passes_m) / max(len(passes_m) + len(passes_t), 1), 1),
            "field_tilt_pct": round(100 * tilt_m / max(tilt_m + tilt_t, 1), 1) if tilt_m + tilt_t else None,
            "xt_15": round(15 * float(pd.to_numeric(mine["delta_xt"], errors="coerce").clip(lower=0).sum()) / dur, 3)
            if "delta_xt" in mine else None,
            "finalizacoes_15": p15(len(sh_m)), "xg_15": round(15 * xg(sh_m) / dur, 2),
            "finalizacoes_sofridas_15": p15(len(sh_t)), "xg_sofrido_15": round(15 * xg(sh_t) / dur, 2),
            "pressoes_15": p15(int((mine["type_name"] == "Pressure").sum())),
            "recuperacoes_15": p15(int((mine["type_name"] == "Ball Recovery").sum()))}


def _score_at(d: pd.DataFrame, team: str, minute: float) -> str:
    sh = d[(d["type_name"] == "Shot") & (d.get("shot_outcome_name") == "Goal") & (d["_m"] < minute)]
    own = d[(d["type_name"] == "Own Goal For") & (d["_m"] < minute)] if "type_name" in d else d.iloc[0:0]
    g = int((sh["team_name"] == team).sum()) + int((own["team_name"] == team).sum())
    o = int((sh["team_name"] != team).sum()) + int((own["team_name"] != team).sum())
    return f"{g} x {o}"


def substitution_impact(df: pd.DataFrame, team: str, window: float = 15.0) -> Dict[str, Any]:
    """Cada troca (ou grupo de trocas no mesmo minuto): janela antes × depois, com placar e trocas simultâneas."""
    d = _play(df).copy()
    d["_m"] = _abs_min(d)
    subs = d[(d["type_name"] == "Substitution") & (d["team_name"] == team)]
    if subs.empty:
        return {"equipe": team, "trocas": []}
    end = float(d["_m"].max())
    rows = []
    for minute, g in subs.groupby(subs["_m"].round(0)):
        m = float(g["_m"].min())
        a, b = max(m - window, 0), min(m + window, end)
        if b - m < 4 or m - a < 4:
            continue                                    # janela curta demais para comparar
        before, after = _window_stats(d, team, a, m), _window_stats(d, team, m, b)
        others = d[(d["type_name"] == "Substitution") & (d["team_name"] != team) & (abs(d["_m"] - m) <= 5)]
        goals_in = d[(d["type_name"] == "Shot") & (d.get("shot_outcome_name") == "Goal") & (d["_m"] >= a) & (d["_m"] < b)]
        delta = {k: round(after[k] - before[k], 3) for k in before if isinstance(before[k], (int, float)) and
                 isinstance(after.get(k), (int, float)) and k != "minutos" and before[k] is not None}
        rows.append({"minuto": int(m) + 1, "entrou": [str(x) for x in g.get("substitution_replacement_name", pd.Series(dtype=object)).dropna()],
                     "saiu": g["player_name"].astype(str).tolist(), "placar_na_troca": _score_at(d, team, m),
                     "antes": before, "depois": after, "variacao": delta,
                     "trocas_do_rival_perto": int(len(others)), "gols_na_janela": int(len(goals_in)),
                     "aviso": "associação no tempo, não causa" + (" — o rival também mexeu" if len(others) else "")
                              + (" — houve gol na janela (o placar muda o comportamento)" if len(goals_in) else "")})
    return {"equipe": team, "janela_min": window, "trocas": rows}


# ------------------------------------------------------------------ estado do jogo
def game_state(df: pd.DataFrame, team: str) -> Dict[str, Any]:
    """Minutos e produção por 15 min com a equipe vencendo, empatando e perdendo."""
    d = _play(df).copy()
    d["_m"] = _abs_min(d)
    goals = d[(d["type_name"] == "Shot") & (d.get("shot_outcome_name") == "Goal")][["_m", "team_name"]].values.tolist()
    marks = [0.0] + [float(m) for m, _ in goals] + [float(d["_m"].max())]
    states: Dict[str, Dict[str, Any]] = {}
    g = o = 0
    for i in range(len(marks) - 1):
        a, b = marks[i], marks[i + 1]
        stt = "vencendo" if g > o else "perdendo" if g < o else "empatando"
        if b - a > 0.5:
            ws = _window_stats(d, team, a, b)
            acc = states.setdefault(stt, {"minutos": 0.0, "_sum": {}})
            acc["minutos"] += ws["minutos"]
            for k, v in ws.items():
                if k != "minutos" and isinstance(v, (int, float)):
                    acc["_sum"][k] = acc["_sum"].get(k, 0.0) + v * ws["minutos"]
        if i < len(goals):
            if goals[i][1] == team:
                g += 1
            else:
                o += 1
    out = {}
    for stt, acc in states.items():
        m = acc["minutos"]
        out[stt] = {"minutos": round(m, 1), "amostra_pequena": m < 15,
                    **{k: round(v / m, 1 if k.endswith("pct") else 2) for k, v in acc["_sum"].items()}}
    return {"equipe": team, "estados": out, "janela_min": 15}
