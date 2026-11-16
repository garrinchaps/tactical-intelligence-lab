"""
Blocos de evidência para perguntas táticas específicas (v36, rodada 3). Cada bloco responde UMA pergunta com números
da partida; nada é estimado sem dizer como. Coordenadas no padrão StatsBomb: cada equipe ataca para a direita nos
próprios eventos; y pequeno = lado ESQUERDO de quem ataca.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

LANES = [("corredor esquerdo", -5, 16), ("meio-espaço esquerdo", 16, 30), ("corredor central", 30, 50),
         ("meio-espaço direito", 50, 64), ("corredor direito", 64, 85)]
GOOD = ["Won", "Success", "Complete", "Success In Play", "Success Out"]


def _r(v, nd=2):
    try:
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), nd)
    except Exception:
        return None


def _col(d: pd.DataFrame, c: str, default=None) -> pd.Series:
    return d[c] if c in d else pd.Series(default, index=d.index)


def _lane(y: float) -> str:
    for name, a, b in LANES:
        if a <= y < b:
            return name
    return "corredor central"


def _side_of_defense(lane: str) -> str:
    """Corredor de quem ataca → lado da defesa de quem defende (esquerda do ataque = direita da defesa)."""
    return {"corredor esquerdo": "lado direito", "meio-espaço esquerdo": "meio-espaço direito",
            "corredor central": "miolo da zaga", "meio-espaço direito": "meio-espaço esquerdo",
            "corredor direito": "lado esquerdo"}.get(lane, lane)


def _shots(d: pd.DataFrame, team: str) -> pd.DataFrame:
    s = d[(d["team_name"] == team) & (d["type_name"] == "Shot")]
    if "period" in s:                                   # disputa de pênaltis (período 5) não é finalização do jogo
        s = s[pd.to_numeric(s["period"], errors="coerce").fillna(1) < 5]
    return s


def _xg(s: pd.DataFrame) -> float:
    return float(pd.to_numeric(_col(s, "shot_statsbomb_xg", 0), errors="coerce").fillna(0).sum())


def _goals(s: pd.DataFrame) -> int:
    return int((_col(s, "shot_outcome_name") == "Goal").sum())


def _sorted(d: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("period", "time_seconds", "index_num") if c in d]
    return d.sort_values(cols) if cols else d


# ------------------------------------------------------------------ corredores
def corridors(df: pd.DataFrame, team: str) -> Dict[str, Any]:
    d = df[df["team_name"] == team]
    prog = d[(_col(d, "is_progressive_action", 0).fillna(0) == 1) & d["type_name"].isin(["Pass", "Carry"])]
    prog = prog[_col(prog, "is_pass_completed", 1).fillna(1) != 0]
    ent = d[_col(d, "is_box_entry", 0).fillna(0) == 1]
    out = []
    for name, a, b in LANES:
        p = prog[(prog["y"] >= a) & (prog["y"] < b)]
        e = ent[(ent["y"] >= a) & (ent["y"] < b)]
        out.append({"corredor": name, "progressoes": int(len(p)), "entradas_na_area": int(len(e)),
                    "xt": _r(pd.to_numeric(_col(p, "delta_xt", 0), errors="coerce").clip(lower=0).sum(), 3),
                    "principais": p.groupby("player_name").size().sort_values(ascending=False).head(2).to_dict()})
    tot = sum(x["progressoes"] for x in out)
    for x in out:
        x["pct"] = _r(100 * x["progressoes"] / tot, 1) if tot else None
    return {"equipe": team, "corredores": sorted(out, key=lambda x: -(x["xt"] or 0)), "progressoes_total": tot,
            "amostra_N": int(len(prog))}


# ------------------------------------------------------------------ como sofreu
def conceded_how(df: pd.DataFrame, defender: str, attacker: str) -> Dict[str, Any]:
    d = _sorted(df)
    s = _shots(d, attacker)
    att = d[d["team_name"] == attacker]
    cats: Dict[str, Dict[str, float]] = {}

    def add(cat, row):
        c = cats.setdefault(cat, {"finalizacoes": 0, "xg": 0.0, "gols": 0})
        c["finalizacoes"] += 1
        c["xg"] += float(pd.to_numeric(pd.Series([row.get("shot_statsbomb_xg")]), errors="coerce").fillna(0).iloc[0])
        c["gols"] += int(row.get("shot_outcome_name") == "Goal")

    for _, sh in s.iterrows():
        pp = str(sh.get("play_pattern_name") or "")
        prev = att[(att.get("possession") == sh.get("possession")) & (att.index < sh.name) & (att["type_name"] == "Pass")] \
            if "possession" in att else att.iloc[0:0]
        last = prev.iloc[-1] if len(prev) else None
        st_type = str(sh.get("shot_type_name") or "")
        if st_type in ("Penalty", "Free Kick", "Corner") or (pp in ("From Corner", "From Free Kick") and len(prev) <= 3):
            add("pênalti" if st_type == "Penalty" else "bola parada", sh)
        elif pp == "From Counter":
            add("contra-ataque", sh)
        elif last is not None and bool(last.get("is_pass_through_ball") or last.get("pass_through_ball")):
            add("bola nas costas (enfiada)", sh)
        elif last is not None and bool(last.get("is_pass_cross")):
            add("cruzamento pelos lados", sh)
        elif last is not None and float(last.get("pass_length") or 0) >= 32:
            add("bola longa", sh)
        elif last is not None and 30 <= float(last.get("end_y") or 40) <= 50:
            add("infiltração pelo meio", sh)
        elif last is not None:
            add("jogada pelos lados (sem cruzamento)", sh)
        else:
            add("jogada individual / rebote", sh)
    rows = [{"tipo": k, "finalizacoes": v["finalizacoes"], "xg": _r(v["xg"]), "gols": v["gols"]} for k, v in cats.items()]
    rows.sort(key=lambda r: (-(r["xg"] or 0), -r["finalizacoes"]))
    return {"defensor": defender, "atacante": attacker, "tipos": rows, "finalizacoes": int(len(s)), "xg": _r(_xg(s)),
            "gols": _goals(s), "amostra_N": int(len(s))}


# ------------------------------------------------------------------ entre linhas
def between_lines(df: pd.DataFrame, attacker: str, defender: str) -> Dict[str, Any]:
    d = df[(df["team_name"] == attacker) & (df["type_name"] == "Pass") & (_col(df, "is_pass_completed", 0) == 1)]
    z = d[(d["end_x"] >= 72) & (d["end_x"] < 102) & (d["end_y"] >= 18) & (d["end_y"] <= 62)]
    by = z.groupby("pass_recipient_name").size().sort_values(ascending=False)
    shots_after = 0
    if "possession" in df:
        poss = set(z["possession"].dropna())
        shots_after = int(df[(df["team_name"] == attacker) & (df["type_name"] == "Shot") & df["possession"].isin(poss)]
                          ["possession"].nunique())
    halves = z.groupby("period").size().to_dict() if "period" in z else {}
    return {"atacante": attacker, "defensor": defender, "recepcoes_entre_linhas": int(len(z)),
            "posses_que_terminaram_em_finalizacao": shots_after, "quem_recebeu": by.head(4).to_dict(),
            "quem_passou": z.groupby("player_name").size().sort_values(ascending=False).head(3).to_dict(),
            "por_tempo": {int(k): int(v) for k, v in halves.items()}, "amostra_N": int(len(z)),
            "zona": "entre a linha de defesa e a de meio-campo do rival, pelo centro (x 72–102, y 18–62)"}


# ------------------------------------------------------------------ eficiência
def efficiency(df: pd.DataFrame, teams: List[str]) -> Dict[str, Any]:
    out = {}
    for t in teams:
        s = _shots(df, t)
        xg = pd.to_numeric(_col(s, "shot_statsbomb_xg", 0), errors="coerce").fillna(0)
        on = _col(s, "shot_outcome_name").isin(["Goal", "Saved", "Saved To Post"])
        g = _goals(s)
        big = s[xg >= 0.3]
        ent = int((_col(df[df["team_name"] == t], "is_box_entry", 0).fillna(0) == 1).sum())
        out[t] = {"finalizacoes": int(len(s)), "no_alvo": int(on.sum()), "gols": g, "xg": _r(xg.sum()),
                  "xg_por_finalizacao": _r(xg.mean()) if len(s) else None, "gols_menos_xg": _r(g - xg.sum()),
                  "conversao_pct": _r(100 * g / len(s), 1) if len(s) else None,
                  "grandes_chances": int(len(big)), "grandes_chances_convertidas": _goals(big),
                  "entradas_na_area": ent, "finalizacoes_por_entrada": _r(len(s) / ent, 2) if ent else None}
    return {"equipes": out, "amostra_N": int(sum(v["finalizacoes"] for v in out.values()))}


# ------------------------------------------------------------------ momentos
def moments(df: pd.DataFrame, teams: List[str], step: int = 15) -> Dict[str, Any]:
    end = int(df["minute"].max()) + 1 if "minute" in df else 90
    rows = []
    for a in range(0, end, step):
        b = a + step
        w = df[(df["minute"] >= a) & (df["minute"] < b)]
        row = {"janela": f"{a}–{min(b, end)}'"}
        for t in teams:
            s = _shots(w, t)
            row[t] = {"finalizacoes": int(len(s)), "xg": _r(_xg(s)), "gols": _goals(s),
                      "entradas_na_area": int((_col(w[w["team_name"] == t], "is_box_entry", 0).fillna(0) == 1).sum())}
        rows.append(row)
    best = {t: max(rows, key=lambda r: (r[t]["xg"] or 0, r[t]["entradas_na_area"]))["janela"] for t in teams} if rows else {}
    return {"janelas": rows, "melhor_janela": best, "amostra_N": int(len(df))}


# ------------------------------------------------------------------ jogadas dos gols
def goal_buildup(df: pd.DataFrame, team: str) -> Dict[str, Any]:
    d = _sorted(df)
    sh = _shots(d, team)
    goals = sh[_col(sh, "shot_outcome_name") == "Goal"]
    out, pattern = [], {}
    for _, g in goals.iterrows():
        chain = d[(d.get("possession") == g.get("possession")) & (d["team_name"] == team) & (d.index <= g.name)] \
            if "possession" in d else d.iloc[0:0]
        passes = chain[chain["type_name"] == "Pass"]
        start = chain.iloc[0] if len(chain) else g
        last = passes.iloc[-1] if len(passes) else None
        dur = float(g.get("time_seconds", 0) - start.get("time_seconds", 0)) if "time_seconds" in d else None
        pp = str(g.get("play_pattern_name") or "")
        if str(g.get("shot_type_name") or "") == "Penalty":
            kind = "pênalti"
        elif pp in ("From Corner", "From Free Kick") and len(passes) <= 3:
            kind = "bola parada"
        elif last is not None and bool(last.get("is_pass_cross")):
            kind = "cruzamento"
        elif last is not None and bool(last.get("is_pass_through_ball") or last.get("pass_through_ball")):
            kind = "bola enfiada nas costas"
        elif dur is not None and dur <= 15 and float(start.get("x") or 0) >= 60:
            kind = "roubada no ataque e finalização rápida"
        elif dur is not None and dur <= 15:
            kind = "contra-ataque"
        elif len(passes) >= 6:
            kind = "posse longa trabalhada"
        else:
            kind = "jogada curta / individual"
        pattern[kind] = pattern.get(kind, 0) + 1
        out.append({"minuto": int(g["minute"]) + 1, "jogador": g.get("player_name"), "tipo": kind,
                    "passes_na_jogada": int(len(passes)), "segundos": _r(dur, 0),
                    "inicio": "campo de ataque" if float(start.get("x") or 0) >= 60 else "campo de defesa",
                    "ultimo_passe": last.get("player_name") if last is not None else None,
                    "corredor_do_ultimo_passe": _lane(float(last.get("y") or 40)) if last is not None else None})
    return {"equipe": team, "gols": out, "padroes": dict(sorted(pattern.items(), key=lambda kv: -kv[1])),
            "amostra_N": int(len(goals))}


# ------------------------------------------------------------------ duplas
def combinations(df: pd.DataFrame, team: Optional[str] = None, top: int = 5) -> Dict[str, Any]:
    d = df[(df["type_name"] == "Pass") & (_col(df, "is_pass_completed", 0) == 1) & df["pass_recipient_name"].notna()]
    if team:
        d = d[d["team_name"] == team]
    d = d.assign(xt=pd.to_numeric(_col(d, "delta_xt", 0), errors="coerce").fillna(0).clip(lower=0),
                 prog=(_col(d, "is_progressive_action", 0).fillna(0) == 1).astype(int))
    g = d.groupby(["player_name", "pass_recipient_name", "team_name"]).agg(passes=("xt", "size"), xt=("xt", "sum"),
                                                                           progressivos=("prog", "sum")).reset_index()
    g = g.sort_values(["xt", "passes"], ascending=False).head(top)
    return {"equipe": team or "ambas", "duplas": [{"de": r.player_name, "para": r.pass_recipient_name, "equipe": r.team_name,
                                                   "passes": int(r.passes), "xt": _r(r.xt, 3), "progressivos": int(r.progressivos)}
                                                  for r in g.itertuples()], "amostra_N": int(len(d))}


# ------------------------------------------------------------------ erros que viraram perigo
def dangerous_errors(df: pd.DataFrame, team: Optional[str], position: Optional[str] = None, top: int = 5) -> Dict[str, Any]:
    from src.metrics.player_rating import sector

    d = _sorted(df)
    rows: Dict[str, Dict[str, Any]] = {}
    losses = d[(_col(d, "is_turnover", 0).fillna(0) == 1) | (d["type_name"] == "Error")]
    if team:
        losses = losses[losses["team_name"] == team]
    pos = d.groupby("player_name")["position_name"].agg(lambda s: s.dropna().mode().iloc[0] if s.dropna().size else "") \
        if "position_name" in d else pd.Series(dtype=str)
    for _, r in losses.iterrows():
        p = r.get("player_name")
        if not isinstance(p, str):
            continue
        if position and sector(pos.get(p, "")) != position:
            continue
        nxt = d[(d["period"] == r["period"]) & (d["time_seconds"] > r["time_seconds"]) &
                (d["time_seconds"] <= r["time_seconds"] + 15)] if "time_seconds" in d else d.iloc[0:0]
        sh = nxt[(nxt["team_name"] != r["team_name"]) & (nxt["type_name"] == "Shot")]
        x = rows.setdefault(p, {"jogador": p, "equipe": r["team_name"], "posicao": pos.get(p, ""), "perdas": 0,
                                "viraram_finalizacao": 0, "xg_cedido": 0.0, "gols_sofridos": 0})
        x["perdas"] += 1
        if len(sh):
            x["viraram_finalizacao"] += 1
            x["xg_cedido"] += _xg(sh.head(1))
            x["gols_sofridos"] += _goals(sh.head(1))
    out = sorted(rows.values(), key=lambda x: (-x["viraram_finalizacao"], -x["xg_cedido"], -x["perdas"]))
    for x in out:
        x["xg_cedido"] = _r(x["xg_cedido"])
    return {"equipe": team or "ambas", "filtro": position, "jogadores": [x for x in out if x["viraram_finalizacao"]][:top]
            or out[:top], "criterio": "perda de bola (ou erro) seguida de finalização do rival em até 15 s",
            "amostra_N": int(len(losses))}


# ------------------------------------------------------------------ diagnóstico dos defensores
def defenders_diag(df: pd.DataFrame, team: str) -> Dict[str, Any]:
    from src.metrics.player_rating import match_ratings

    r = match_ratings(df, team)
    if r.empty:
        return {"equipe": team, "defensores": [], "amostra_N": 0}
    dfn = r[r["setor"] == "defesa"]
    d = df[df["team_name"] == team]
    err = dangerous_errors(df, team, "defesa", top=20)
    err_by = {x["jogador"]: x for x in err["jogadores"]}
    out = []
    for x in dfn.to_dict("records"):
        p = x["jogador"]
        ev = d[d["player_name"] == p]
        aerial_lost = int(((ev["type_name"] == "Duel") & (_col(ev, "duel_type_name") == "Aerial Lost")).sum())
        dribbled = int((ev["type_name"] == "Dribbled Past").sum())
        clear = int((ev["type_name"] == "Clearance").sum())
        own_half_loss = int(((_col(ev, "is_turnover", 0).fillna(0) == 1) & (ev["x"] < 60)).sum())
        e = err_by.get(p, {})
        issues = []
        if e.get("viraram_finalizacao"):
            issues.append(("perda(s) que virou(aram) finalização do rival", e["viraram_finalizacao"],
                           "simplificar a saída sob pressão: passe para o lado ou bola longa, sem conduzir"))
        if dribbled >= 2:
            issues.append(("vezes driblado", dribbled, "não dar o bote: temporizar e esperar a cobertura"))
        if aerial_lost >= 2:
            issues.append(("duelos aéreos perdidos", aerial_lost, "antecipar a disputa e marcar por trás do centroavante"))
        if own_half_loss >= 3:
            issues.append(("bolas perdidas no próprio campo", own_half_loss, "oferecer linha de passe mais curta ao volante"))
        if x.get("passes_errados", 0) >= 6:
            issues.append(("passes errados", int(x["passes_errados"]), "diminuir o risco do passe vertical na construção"))
        out.append({"jogador": p, "posicao": x.get("posicao"), "minutos": x.get("minutos"), "nota": x.get("nota"),
                    "desarmes": int(x.get("desarmes", 0)), "interceptacoes": int(x.get("interceptacoes", 0)),
                    "cortes": clear, "driblado": dribbled, "aereos_perdidos": aerial_lost,
                    "perdas_proprio_campo": own_half_loss, "perdas_que_viraram_finalizacao": e.get("viraram_finalizacao", 0),
                    "problemas": [{"o_que": a, "quantas": b, "correcao": c} for a, b, c in issues]})
    out.sort(key=lambda z: (z["nota"] is None, z["nota"] or 0))
    return {"equipe": team, "defensores": out, "amostra_N": int(len(dfn))}


# ------------------------------------------------------------------ plano para atacar uma defesa
def attack_plan(df: pd.DataFrame, attacker: str, defender: str) -> Dict[str, Any]:
    cor = corridors(df, attacker)
    how = conceded_how(df, defender, attacker)
    errs = dangerous_errors(df, defender, None, top=3)
    dd = df[df["team_name"] == defender]
    loss = dd[(_col(dd, "is_turnover", 0).fillna(0) == 1) & (dd["x"] < 60)]
    zones = loss.assign(l=loss["y"].map(_lane)).groupby("l").size().sort_values(ascending=False).head(2).to_dict()
    dribbled = dd[dd["type_name"] == "Dribbled Past"].groupby("player_name").size().sort_values(ascending=False).head(2).to_dict()
    aerial = dd[(dd["type_name"] == "Duel") & (_col(dd, "duel_type_name") == "Aerial Lost")].groupby("player_name").size() \
        .sort_values(ascending=False).head(2).to_dict()
    return {"atacante": attacker, "defensor": defender,
            "melhor_corredor": cor["corredores"][0] if cor["corredores"] else None,
            "corredores": cor["corredores"][:3], "como_o_defensor_sofreu": how["tipos"][:3],
            "perdas_do_defensor_no_proprio_campo": int(len(loss)), "zonas_das_perdas": zones,
            "defensores_mais_driblados": dribbled, "perdeu_mais_no_alto": aerial,
            "erros_que_viraram_finalizacao": errs["jogadores"][:3], "amostra_N": int(len(df))}
