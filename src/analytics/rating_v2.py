"""
Modelo de avaliação individual 3.0 — motor estatístico TRANSPARENTE (sem caixa-preta).

Jogadores de linha: 7 dimensões (0–10) — produção ofensiva, criação, progressão, defesa, eficiência, disciplina e
trabalho coletivo observável — com pesos pela FUNÇÃO exercida no jogo e blend de papéis quando os eventos documentam mudanças de função.
Goleiros: 6 dimensões — defesa de finalizações 30%, posicionamento 15%, jogo aéreo 10%, distribuição 15%,
decisões/segurança 20%, cobertura 10%.

Como cada número vira nota:
1. Indicador por 90 min (ou taxa) → percentil contra jogadores da MESMA função na base de referência.
2. Percentil → nota pela régua 3.0: P5=3,8 · P10=4,5 · P25=5,5 · P50=6,4 · P75=7,4 · P90=8,6 · P95=9,25 · P99=10
   (invertida em indicadores negativos, como perdas e erros).
3. Dimensão = média ponderada dos indicadores que EXISTEM. Indicador sem dado não vira zero: fica fora e a confiança cai.
4. Nota = Σ peso × dimensão (pesos renormalizados sobre as dimensões observadas).
5. Pouca amostra puxa o desempenho para a referência neutra 6,4, conforme minutos observados.
6. Nota final = desempenho + ajuste limitado de momentos decisivos; também são reportados desempenho-base, impacto e confiança.

Limites honestos: papel misto é aproximado pela distribuição das posições anotadas nos eventos, não por tracking minuto
a minuto. Sem tracking nem vídeo, fechamentos de linhas, movimentos de atração e coberturas sem ação registrada não são
observáveis. Gols evitados em fontes sem xGOT são identificados como proxy de xG pré-chute, nunca como xGOT.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Régua 3.0: centro neutro próximo de 6,4 (entre as bases divulgadas de 6,0–6,5),
# com cauda alta mais exigente. P99 continua raro; os percentis são calibrados por função.
PCT_TABLE = [(0, 3.0), (5, 3.8), (10, 4.5), (25, 5.5), (50, 6.4), (75, 7.4), (90, 8.6), (95, 9.25), (99, 10.0), (100, 10.0)]
REF_SCORE = 6.4
RATING_ENGINE_VERSION = "3.0.1"

DIMS = ["ofensiva", "criacao", "progressao", "defesa", "eficiencia", "disciplina", "tatica"]
DIM_PT = {"ofensiva": "Produção ofensiva", "criacao": "Criação e construção", "progressao": "Progressão",
          "defesa": "Contribuição defensiva", "eficiencia": "Eficiência técnica", "disciplina": "Disciplina e segurança",
          "tatica": "Trabalho coletivo e sem bola (observável)"}
WEIGHTS = {   # % por função (cada linha soma 100)
    "centroavante": [35, 15, 12, 8, 15, 5, 10], "ponta": [27, 18, 20, 10, 12, 5, 8],
    "meia ofensivo": [20, 25, 18, 10, 12, 5, 10], "meia central": [14, 22, 20, 17, 12, 5, 10],
    "volante": [8, 15, 15, 32, 12, 8, 10], "lateral": [12, 15, 18, 25, 12, 8, 10], "zagueiro": [5, 10, 10, 40, 15, 10, 10],
}
GK_DIMS = ["defesas", "posicionamento", "aereo", "distribuicao", "seguranca", "cobertura"]
GK_DIM_PT = {"defesas": "Defesa de finalizações", "posicionamento": "Posicionamento e leitura (não observado)",
             "aereo": "Jogo aéreo e controle da área", "distribuicao": "Distribuição e construção",
             "seguranca": "Decisões e segurança", "cobertura": "Cobertura e participação defensiva"}
GK_WEIGHTS = [30, 15, 10, 15, 20, 10]

# indicador → (dimensão, peso dentro da dimensão, maior_é_melhor)
INDICATORS: Dict[str, tuple] = {
    "gols_np90": ("ofensiva", 1.5, True), "gols_pen90": ("ofensiva", 0.5, True), "xg90": ("ofensiva", 1.5, True),
    "no_alvo90": ("ofensiva", 1.0, True), "fin_area90": ("ofensiva", 0.7, True),
    "chances_perdidas_xg90": ("ofensiva", 0.8, False),           # grandes chances desperdiçadas, pelo xG perdido
    "assist90": ("criacao", 1.0, True), "xa90": ("criacao", 1.5, True), "decisivos90": ("criacao", 1.3, True),
    "passes_area90": ("criacao", 1.0, True), "quebra_linha90": ("criacao", 0.8, True),
    "cruz_certos90": ("criacao", 0.5, True), "enfiadas90": ("criacao", 0.6, True),
    "prog_passes90": ("progressao", 1.2, True), "prog_carries90": ("progressao", 1.0, True),
    "xt90": ("progressao", 1.5, True), "dribles90": ("progressao", 0.7, True), "entradas_terco90": ("progressao", 0.7, True),
    "entradas_area90": ("progressao", 0.8, True),
    "desarmes_ganhos90": ("defesa", 1.0, True), "intercept90": ("defesa", 1.3, True), "cortes90": ("defesa", 0.8, True),
    "bloqueios90": ("defesa", 0.8, True), "recup90": ("defesa", 0.8, True), "aereos_ganhos90": ("defesa", 0.7, True),
    "driblado90": ("defesa", 0.9, False),
    "passe_pct_dificil": ("eficiencia", 1.3, True), "passe_pct": ("eficiencia", 0.6, True),
    "perdas_por_toque": ("eficiencia", 1.0, False), "perdas_perigosas90": ("eficiencia", 1.0, False),
    "amarelos": ("disciplina", 1.0, False), "faltas90": ("disciplina", 0.6, False),
    "entre_linhas90": ("tatica", 1.0, True), "participacao_pct": ("tatica", 1.0, True),
    "pressao90": ("tatica", 0.8, True), "pressao_campo_rival90": ("tatica", 0.9, True),
    "acoes_defensivas90": ("tatica", 0.7, True), "sprints90": ("tatica", 0.35, True),
}
GK_INDICATORS: Dict[str, tuple] = {
    "defesas90": ("defesas", 0.8, True), "pct_defesas": ("defesas", 1.0, True), "gols_evitados": ("defesas", 1.6, True),
    "saidas_aereas90": ("aereo", 1.0, True), "gk_passe_pct": ("distribuicao", 0.8, True),
    "gk_longos_pct": ("distribuicao", 1.0, True), "gk_prog90": ("distribuicao", 0.8, True),
    "gk_perdas90": ("seguranca", 1.0, False), "gk_erros": ("seguranca", 1.6, False),
    "gk_acoes_fora_area90": ("cobertura", 1.0, True),
}


IND_PT = {
    "gols_np90": "Gols (sem pênalti) /90", "gols_pen90": "Gols de pênalti /90", "xg90": "xG /90", "no_alvo90": "Finalizações no alvo /90",
    "fin_area90": "Finalizações de dentro da área /90", "chances_perdidas_xg90": "xG desperdiçado em chances claras /90",
    "assist90": "Assistências /90", "xa90": "xA (assistências esperadas) /90", "decisivos90": "Passes para finalização /90",
    "passes_area90": "Passes para dentro da área /90", "quebra_linha90": "Passes que quebram linhas /90",
    "cruz_certos90": "Cruzamentos certos /90", "enfiadas90": "Bolas enfiadas /90", "prog_passes90": "Passes progressivos /90",
    "prog_carries90": "Conduções progressivas /90", "xt90": "Ameaça criada (xT) /90", "dribles90": "Dribles /90",
    "entradas_terco90": "Entradas no terço final /90", "entradas_area90": "Entradas na área /90",
    "desarmes_ganhos90": "Desarmes ganhos /90", "intercept90": "Interceptações /90", "cortes90": "Cortes /90",
    "bloqueios90": "Bloqueios /90", "recup90": "Recuperações /90", "aereos_ganhos90": "Duelos aéreos ganhos /90",
    "driblado90": "Vezes driblado /90", "passe_pct_dificil": "Acerto em passes difíceis (%)", "passe_pct": "Acerto de passe (%)",
    "perdas_por_toque": "Perdas por toque na bola", "perdas_perigosas90": "Perdas no próprio campo /90",
    "amarelos": "Cartões amarelos", "faltas90": "Faltas cometidas /90", "entre_linhas90": "Bolas recebidas entre linhas /90",
    "participacao_pct": "Participação na troca de passes (%)", "pressao90": "Pressões /90",
    "acoes_defensivas90": "Ações defensivas /90", "sprints90": "Sprints /90",
    "pressao_campo_rival90": "Pressões no campo rival /90",
    "defesas90": "Defesas /90", "pct_defesas": "Defesas (%)", "gols_evitados": "Gols evitados (proxy informado pela fonte)",
    "saidas_aereas90": "Ações de goleiro na área /90", "gk_passe_pct": "Acerto de passe (%)", "gk_longos_pct": "Acerto em bolas longas (%)",
    "gk_prog90": "Passes progressivos /90", "gk_perdas90": "Perdas /90", "gk_erros": "Erros que deram chance",
    "gk_acoes_fora_area90": "Ações fora da área /90",
}


def outliers(ev: Dict[str, Any], high: float = 85, low: float = 15) -> Dict[str, List[Dict[str, Any]]]:
    """Só o que FOGE da média dos pares: percentil ≥ 85 (força) ou ≤ 15 (fraqueza), já no sentido 'bom'."""
    base = ev.get("base") or []
    fortes = sorted([b for b in base if b["percentil"] >= high], key=lambda b: -b["percentil"])
    fracos = sorted([b for b in base if b["percentil"] <= low], key=lambda b: b["percentil"])
    return {"fortes": fortes, "fracos": fracos}


def role_of(position: Any) -> str:
    p = str(position or "").lower()
    if "goalkeeper" in p or "goleiro" in p:
        return "goleiro"
    if "center back" in p or "centre back" in p or "zagueiro" in p:
        return "zagueiro"
    if "wing back" in p or ("back" in p and ("left" in p or "right" in p)) or "lateral" in p:
        return "lateral"
    if "back" in p or "zagueiro" in p:
        return "zagueiro"
    if "defensive midfield" in p or "volante" in p:
        return "volante"
    if "attacking midfield" in p:
        return "meia ofensivo"
    if "wing" in p or ("midfield" in p and ("left" in p or "right" in p) and "center" not in p):
        return "ponta"
    if "midfield" in p:
        return "meia central"
    if "forward" in p or "striker" in p:
        return "centroavante"
    return "meia central"


def _as_float(value: Any, default: float = 0.0) -> float:
    """Converte estatística opcional sem propagar NaN para o cálculo da nota."""
    try:
        if value is None or pd.isna(value):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def pct_to_score(p: float) -> float:
    xs, ys = zip(*PCT_TABLE)
    return float(np.interp(p, xs, ys))


def minutes_tier(m: float) -> str:
    return ("amostra insuficiente" if m < 15 else "avaliação provisória" if m < 30 else "avaliação parcial" if m < 45
            else "amostra moderada" if m < 60 else "avaliação normal com ressalvas" if m < 90 else "avaliação completa")


def label(n: Optional[float]) -> str:
    if n is None:
        return "sem nota"
    return ("desastrosa" if n < 2 else "muito ruim" if n < 4 else "ruim" if n < 5 else "regular" if n < 6 else
            "razoável" if n < 7 else "boa" if n < 8 else "muito boa" if n < 9 else "excelente" if n < 9.6 else "excepcional")


# ------------------------------------------------------------------ momentos decisivos observáveis
def _shootout_contributions(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    """Atribui defesas da disputa ao goleiro identificado na própria partida; não confunde chute para fora com defesa."""
    from src.metrics.match_facts import _regular

    result: Dict[str, Dict[str, int]] = {}
    if df is None or df.empty or not {"period", "type_name", "team_name", "player_name"}.issubset(df.columns):
        return result
    regular = _regular(df)
    teams = [str(x) for x in df["team_name"].dropna().unique()]
    goalkeepers: Dict[str, str] = {}
    if "position_name" in regular:
        is_gk = regular["position_name"].map(role_of).eq("goleiro")
        gks = regular[is_gk & regular["player_name"].notna()]
        for team, group in gks.groupby("team_name"):
            counts = group["player_name"].value_counts()
            if not counts.empty:
                goalkeepers[str(team)] = str(counts.index[0])
    # Algumas fontes não anotam position_name, mas registram ações próprias do goleiro.
    if "type_name" in regular:
        actions = regular[regular["type_name"].astype(str).str.lower().isin(["goal keeper", "goalkeeper"])]
        for team, group in actions.groupby("team_name"):
            if str(team) not in goalkeepers:
                counts = group["player_name"].dropna().value_counts()
                if not counts.empty:
                    goalkeepers[str(team)] = str(counts.index[0])

    attempts = df[(df["period"] == 5) & (df["type_name"] == "Shot")]
    for shot in attempts.itertuples():
        shooter = str(getattr(shot, "player_name", "") or "")
        shooting_team = str(getattr(shot, "team_name", "") or "")
        outcome = str(getattr(shot, "shot_outcome_name", "") or "")
        if not shooter or not shooting_team:
            continue
        row = result.setdefault(shooter, {"shootout_penaltis_marcados": 0, "shootout_penaltis_perdidos": 0,
                                          "shootout_saves": 0})
        if outcome == "Goal":
            row["shootout_penaltis_marcados"] += 1
        else:
            row["shootout_penaltis_perdidos"] += 1
        if "saved" in outcome.lower():
            defending = next((team for team in teams if team != shooting_team), None)
            keeper = goalkeepers.get(defending or "")
            if keeper:
                gk_row = result.setdefault(keeper, {"shootout_penaltis_marcados": 0,
                                                    "shootout_penaltis_perdidos": 0, "shootout_saves": 0})
                gk_row["shootout_saves"] += 1
    return result


# ------------------------------------------------------------------ indicadores por jogador e partida
def indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Indicadores brutos (por 90 e taxas) de cada jogador numa partida com lances."""
    from src.metrics.match_facts import _minutes, _regular, goals

    if df is None or df.empty:
        return pd.DataFrame()
    d = _regular(df)
    d = d[d["player_name"].notna() & ~d["player_name"].astype(str).str.lower().isin(["não identificado", "nao identificado", "unknown"])]
    mins = _minutes(df)
    gl = goals(df)
    col = lambda c, v=0: d[c] if c in d else pd.Series(v, index=d.index)
    t = d["type_name"]
    shot_rows = d[d["type_name"] == "Shot"]
    has_match_xg = ("shot_statsbomb_xg" in d.columns
                    and pd.to_numeric(shot_rows["shot_statsbomb_xg"], errors="coerce").notna().any())
    has_xa_inputs = has_match_xg and {"possession", "pass_recipient_name", "pass_outcome_name"}.issubset(d.columns)
    # xA: xG das finalizações que vieram do último passe do jogador na mesma posse.
    # Sem xG/posse/recebedor, xA fica ausente, não zero.
    xa: Dict[str, float] = {}
    if has_xa_inputs:
        passes = d[(t == "Pass") & col("pass_outcome_name").isna()]
        for s in d[t == "Shot"].itertuples():
            c = passes[(passes["team_name"] == s.team_name) & (passes["pass_recipient_name"] == s.player_name)
                       & (passes.index < s.Index) & (passes["possession"] == s.possession)]
            if len(c):
                p = str(c.iloc[-1]["player_name"])
                xa[p] = xa.get(p, 0.0) + float(getattr(s, "shot_statsbomb_xg", 0) or 0)
    team_pass = d[t == "Pass"].groupby("team_name").size()
    rows = []
    for (p, team), e in d.groupby(["player_name", "team_name"]):
        m = float(mins.get(p, 0) or 0)
        f = 90.0 / max(m, 1.0)
        et = e["type_name"]
        ps = e[et == "Pass"]
        ok = ps[ps.get("pass_outcome_name").isna()] if "pass_outcome_name" in ps else ps
        hard_mask = pd.Series(False, index=ps.index)
        if "pass_length" in ps:
            hard_mask |= pd.to_numeric(ps["pass_length"], errors="coerce").fillna(0) >= 25
        if {"end_x", "x"}.issubset(ps.columns):
            hard_mask |= (pd.to_numeric(ps["end_x"], errors="coerce")
                          - pd.to_numeric(ps["x"], errors="coerce")) >= 15
        hard = ps[hard_mask]
        hard_ok = hard[hard.get("pass_outcome_name").isna()] if "pass_outcome_name" in hard else hard
        shots = e[et == "Shot"]
        has_player_xg = ("shot_statsbomb_xg" in shots.columns
                         and pd.to_numeric(shots["shot_statsbomb_xg"], errors="coerce").notna().any())
        sxg = (pd.to_numeric(shots["shot_statsbomb_xg"], errors="coerce").fillna(0)
               if "shot_statsbomb_xg" in shots else pd.Series(0.0, index=shots.index))
        has_shot_outcome = "shot_outcome_name" in shots.columns
        shot_outcomes = (shots["shot_outcome_name"].astype(str) if has_shot_outcome
                         else pd.Series("", index=shots.index, dtype=object))
        is_goal = shot_outcomes.eq("Goal")
        is_pen = shots["shot_type_name"].eq("Penalty") if "shot_type_name" in shots else pd.Series(False, index=shots.index)
        on = shot_outcomes.isin(["Goal", "Saved", "Saved To Post"]) if has_shot_outcome else pd.Series(False, index=shots.index)
        outcomes = shot_outcomes
        # Finalização defendida não é erro do atacante: só desvios/traves entram como chance desperdiçada.
        missed = outcomes.str.lower().isin(["off t", "wayward", "post", "miss", "missed"])
        big_missed = sxg[(sxg >= 0.3) & missed].sum()
        carries = e[et == "Carry"]
        touches = int(et.isin(["Pass", "Carry", "Shot", "Dribble", "Ball Receipt*", "Miscontrol", "Dispossessed"]).sum())
        turn = e[e.get("is_turnover", 0) == 1] if "is_turnover" in e else e.iloc[0:0]
        own_half_turn = turn[turn["x"] < 50] if "x" in turn else turn.iloc[0:0]
        duels = e[et == "Duel"]
        has_receipt_data = {"pass_recipient_name", "is_pass_completed", "type_name", "end_x", "end_y"}.issubset(df.columns)
        rec = (df[(df["pass_recipient_name"] == p) & (df["type_name"] == "Pass")
                  & (df["is_pass_completed"] == 1)] if has_receipt_data else df.iloc[0:0])
        between = (rec[(rec["end_x"] >= 72) & (rec["end_x"] < 102) & (rec["end_y"].between(18, 62))]
                   if has_receipt_data else rec)
        error_flag = next((k for k in ("is_error_leading_to_shot", "is_error_leading_to_goal") if k in e), None)
        errors_to_chance = (int(pd.to_numeric(e[error_flag], errors="coerce").fillna(0).astype(bool).sum())
                            if error_flag else None)
        gk = {}
        position_mode = (e["position_name"].dropna().mode().iloc[0]
                         if "position_name" in e and not e["position_name"].dropna().empty else "")
        if role_of(position_mode) == "goleiro":
            faced = d[(d["team_name"] != team) & (d["type_name"] == "Shot")]
            fo = faced.get("shot_outcome_name", pd.Series(dtype=object))
            on_t = faced[fo.isin(["Goal", "Saved", "Saved To Post"])]
            ga = int((on_t.get("shot_outcome_name") == "Goal").sum())
            saves = int(len(on_t) - ga)
            has_faced_xg = ("shot_statsbomb_xg" in on_t.columns
                             and pd.to_numeric(on_t["shot_statsbomb_xg"], errors="coerce").notna().any())
            xg_on = (float(pd.to_numeric(on_t["shot_statsbomb_xg"], errors="coerce").fillna(0).sum())
                     if has_faced_xg else None)
            longp = (ps[pd.to_numeric(ps["pass_length"], errors="coerce").fillna(0) >= 32]
                     if "pass_length" in ps else ps.iloc[0:0])
            longp_ok = longp[longp.get("pass_outcome_name").isna()] if "pass_outcome_name" in longp else longp
            saved_shots = (on_t[on_t["shot_outcome_name"].astype(str).str.contains("Saved", case=False)]
                           if "shot_outcome_name" in on_t else on_t.iloc[0:0])
            saved_xg = (pd.to_numeric(saved_shots["shot_statsbomb_xg"], errors="coerce").fillna(0)
                        if "shot_statsbomb_xg" in saved_shots else pd.Series(dtype=float))
            saved_min = (pd.to_numeric(saved_shots["minute"], errors="coerce").fillna(0)
                         if "minute" in saved_shots else pd.Series(dtype=float))
            key_saves = (int(((saved_xg >= 0.25) & (saved_min >= 85)).sum())
                         if has_match_xg and "minute" in saved_shots else None)
            gk = {"defesas90": saves * f if has_shot_outcome else None,
                  "pct_defesas": 100 * saves / len(on_t) if has_shot_outcome and len(on_t) else None,
                  "gols_evitados": xg_on - ga if xg_on is not None else None,
                  "gols_sofridos": ga if has_shot_outcome else None,
                  "defesas": saves if has_shot_outcome else None,
                  "key_saves": key_saves,
                  "finalizacoes_no_alvo_enfrentadas": int(len(on_t)), "xg_no_alvo_enfrentado": round(xg_on, 2),
                  "saidas_aereas90": int((et == "Goal Keeper").sum()) * f if (et == "Goal Keeper").any() else None,
                  "gk_passe_pct": 100 * len(ok) / len(ps) if len(ps) >= 5 and "pass_outcome_name" in ps else None,
                  "gk_longos_pct": (100 * len(longp_ok) / len(longp)
                                    if len(longp) >= 3 and "pass_outcome_name" in longp else None),
                  "gk_prog90": int((ok["is_progressive_action"] == 1).sum()) * f
                      if "is_progressive_action" in ok else None,
                  "gk_perdas90": len(turn) * f if "is_turnover" in e else None,
                  "gk_erros": errors_to_chance,
                  "gk_acoes_fora_area90": int(((e["x"] > 18) & et.isin(["Clearance", "Interception", "Ball Recovery",
                                                                       "Goal Keeper"])).sum()) * f
                      if "x" in e else None}
        np_goals = int((is_goal & ~is_pen).sum())
        pen_goals = int((is_goal & is_pen).sum())
        # Só penaliza erro que o provedor marque explicitamente como causador de finalização/gol.
        # Um evento genérico "Error" não prova, sozinho, que o erro gerou uma chance.
        pos_series = e["position_name"].dropna().astype(str) if "position_name" in e else pd.Series(dtype=str)
        role_counts = pos_series.map(role_of).value_counts() if not pos_series.empty else pd.Series(dtype=float)
        role_mix = ({str(k): float(v / role_counts.sum()) for k, v in role_counts.items()}
                    if not role_counts.empty and role_counts.sum() else {})
        primary_role = max(role_mix, key=role_mix.get) if role_mix else role_of(
            e["position_name"].dropna().mode().iloc[0] if "position_name" in e and not e["position_name"].dropna().empty else "")
        rows.append({
            "jogador": p, "equipe": team, "posicao": e["position_name"].dropna().mode().iloc[0] if "position_name" in e
            and not e["position_name"].dropna().empty else "", "funcao": primary_role, "role_mix": role_mix, "minutos": m,
            "gols": np_goals + pen_goals, "gols_penalti": pen_goals,
            "assistencias": sum(1 for g in gl if g.get("assistencia") == p),
            "gols_np90": np_goals * f, "gols_pen90": pen_goals * f,
            "xg90": float(sxg.sum()) * f if has_player_xg else None,
            "xg": round(float(sxg.sum()), 2) if has_player_xg else None,
            "no_alvo90": int(on.sum()) * f if has_shot_outcome else None,
            "fin_area90": int(((shots["x"] >= 102) & shots["y"].between(18, 62)).sum()) * f
                if {"x", "y"}.issubset(shots.columns) else None,
            "chances_perdidas_xg90": float(big_missed) * f if has_player_xg and has_shot_outcome else None,
            "chances_claras_perdidas": int(((sxg >= 0.3) & missed).sum()) if has_player_xg and has_shot_outcome else None,
            "assist90": sum(1 for g in gl if g.get("assistencia") == p) * f,
            "xa90": xa.get(p, 0.0) * f if has_xa_inputs else None,
            "xa": round(xa.get(p, 0.0), 2) if has_xa_inputs else None,
            "decisivos90": 0.0,
            "passes_area90": int((ok["end_in_box"] == 1).sum()) * f
                if "end_in_box" in ok and "pass_outcome_name" in ok else None,
            "quebra_linha90": int((ok["is_line_breaking_pass"] == 1).sum()) * f
                if "is_line_breaking_pass" in ok and "pass_outcome_name" in ok else None,
            "cruz_certos90": int(ok["is_pass_cross"].fillna(0).astype(bool).sum()) * f
                if "is_pass_cross" in ok and "pass_outcome_name" in ok else None,
            "enfiadas90": int(ok["is_pass_through_ball"].fillna(0).astype(bool).sum()) * f
                if "is_pass_through_ball" in ok and "pass_outcome_name" in ok else None,
            "prog_passes90": int((ok["is_progressive_action"] == 1).sum()) * f
                if "is_progressive_action" in ok and "pass_outcome_name" in ok else None,
            "prog_carries90": int((carries["is_progressive_action"] == 1).sum()) * f if "is_progressive_action" in carries else None,
            "xt90": float(pd.to_numeric(e["delta_xt"], errors="coerce").fillna(0).clip(lower=0).sum()) * f
                if "delta_xt" in e else None,
            "dribles90": int((et == "Dribble").sum()) * f,
            "entradas_terco90": int((e.get("is_final_third_entry", 0) == 1).sum()) * f if "is_final_third_entry" in e else None,
            "entradas_area90": int((e.get("is_box_entry", 0) == 1).sum()) * f if "is_box_entry" in e else None,
            "desarmes_ganhos90": int(((et == "Duel") & (e.get("duel_type_name") == "Tackle")
                                      & e.get("duel_outcome_name").isin(["Won", "Success In Play", "Success Out"])).sum()) * f
            if "duel_type_name" in e and "duel_outcome_name" in e else None,
            "intercept90": int((et == "Interception").sum()) * f, "cortes90": int((et == "Clearance").sum()) * f,
            "bloqueios90": int((et == "Block").sum()) * f, "recup90": int((et == "Ball Recovery").sum()) * f,
            "aereos_ganhos90": int(((et == "Duel") & (e.get("duel_type_name") == "Aerial Won")).sum()) * f
            if "duel_type_name" in e else None,
            "driblado90": int((et == "Dribbled Past").sum()) * f,
            "passe_pct": 100 * len(ok) / len(ps) if len(ps) >= 5 and "pass_outcome_name" in ps else None,
            "passe_pct_dificil": (100 * len(hard_ok) / len(hard)
                                  if len(hard) >= 4 and "pass_outcome_name" in hard else None),
            "perdas_por_toque": (len(turn) / touches
                                 if touches >= 10 and "is_turnover" in e else None),
            "perdas_perigosas90": (len(own_half_turn) * f
                                   if "is_turnover" in e and "x" in e else None),
            "amarelos": int((e["foul_committed_card_name"] == "Yellow Card").sum()) if "foul_committed_card_name" in e else None,
            "vermelhos": int(e["foul_committed_card_name"].isin(["Red Card", "Second Yellow"]).sum())
                if "foul_committed_card_name" in e else None,
            "faltas90": int((et == "Foul Committed").sum()) * f,
            "erros_que_viraram_chance": errors_to_chance,
            "pressao90": int((et == "Pressure").sum()) * f if "Pressure" in set(d["type_name"].dropna().astype(str)) else None,
            "acoes_defensivas90": int(pd.to_numeric(e["is_defensive_action"], errors="coerce").fillna(0).sum()) * f
                if "is_defensive_action" in e else None,
            "sprints90": None,
            "entre_linhas90": len(between) * f if has_receipt_data else None,
            "participacao_pct": (100 * (len(ps) + len(rec)) / max(2 * int(team_pass.get(team, 0)), 1)
                                 if has_receipt_data else None),
            "pressao_campo_rival90": int(((et == "Pressure") & (e["x"] >= 60)).sum()) * f
                if (t == "Pressure").any() and "x" in e else None,
            **gk,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        from src.metrics.match_facts import player_match_stats

        pm = player_match_stats(df)
        if not pm.empty and "passes_decisivos" in pm:
            kp = dict(zip(pm["jogador"], pm["passes_decisivos"]))
            out["decisivos90"] = [kp.get(p, 0) * 90 / max(m, 1) for p, m in zip(out["jogador"], out["minutos"])]
            out["passes_decisivos"] = out["jogador"].map(kp).fillna(0).astype(int)
        # A distribuição de papéis vem das posições registradas nos eventos. É uma aproximação pela participação
        # das ações em cada posição, não tracking minuto a minuto.
        if "funcao" not in out:
            out["funcao"] = out["posicao"].map(role_of)
        else:
            out["funcao"] = out["funcao"].fillna(out["posicao"].map(role_of))
        shootout = _shootout_contributions(df)
        for idx, player in out["jogador"].items():
            extra = shootout.get(str(player), {})
            for key, value in extra.items():
                out.loc[idx, key] = value
        for key in ("shootout_penaltis_marcados", "shootout_penaltis_perdidos", "shootout_saves"):
            if key not in out:
                out[key] = 0
            out[key] = pd.to_numeric(out[key], errors="coerce").fillna(0).astype(int)
    return out


# ------------------------------------------------------------------ referência (percentis por função)
_REF_CACHE: Dict[str, pd.DataFrame] = {}


def reference_pool(extra: Optional[List[pd.DataFrame]] = None) -> pd.DataFrame:
    """
    Base de comparação: indicadores de jogadores com ≥ 30 min nas partidas com lances disponíveis (cache em disco em
    data/processed/rating_ref_v2.parquet; sem cache, as partidas de demonstração). Quanto mais partidas, melhor.
    """
    from pathlib import Path

    key = "base"
    if key not in _REF_CACHE:
        p = Path("data/processed/rating_ref_v2.parquet")
        ref = pd.DataFrame()
        if not p.exists() and p.with_name("rating_ref_v2_demo.parquet").exists():
            p = p.with_name("rating_ref_v2_demo.parquet")
        if p.exists():
            try:
                ref = pd.read_parquet(p)
            except Exception:
                ref = pd.DataFrame()
        if ref.empty:
            ref = _demo_reference()
            try:                                      # guarda para não recalcular a cada abertura do app
                p.parent.mkdir(parents=True, exist_ok=True)
                ref.to_parquet(p.with_name("rating_ref_v2_demo.parquet"), index=False)
            except Exception:
                pass
        _REF_CACHE[key] = ref
    ref = _REF_CACHE[key]
    if extra:
        ref = pd.concat([ref] + [x for x in extra if x is not None and not x.empty], ignore_index=True)
    return ref[ref["minutos"] >= 30] if not ref.empty else ref


def _demo_reference() -> pd.DataFrame:
    try:
        from src.connectors.statsbomb_connector import load_demo_events
        from src.ingestion.statsbomb_loader import StatsBombDataLoader
        from src.metrics.xt_model import ExpectedThreatModel
        from src.preprocessing.event_cleaner import EventPreprocessor
    except Exception:
        return pd.DataFrame()
    out = []
    for mid in (3869685, 3869519, 3869552):
        try:
            raw = StatsBombDataLoader._parse_raw_events(None, load_demo_events(mid), mid)
            df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(raw))
            out.append(indicators(df))
        except Exception:
            continue
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def build_reference(dfs: List[pd.DataFrame], path: str = "data/processed/rating_ref_v2.parquet") -> int:
    """Grava a base de referência a partir de várias partidas com lances (rode com muitas partidas para calibrar)."""
    from pathlib import Path

    rows = [indicators(d) for d in dfs if d is not None and not d.empty]
    ref = pd.concat([r for r in rows if not r.empty], ignore_index=True) if rows else pd.DataFrame()
    if ref.empty:
        return 0
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ref.to_parquet(path, index=False)
    _REF_CACHE.clear()
    return int(len(ref))


def _peer_group(ref: pd.DataFrame, funcao: str, role_mix: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    near = {"centroavante": ["centroavante", "ponta"], "ponta": ["ponta", "meia ofensivo", "centroavante"],
            "meia ofensivo": ["meia ofensivo", "meia central", "ponta"], "meia central": ["meia central", "volante", "meia ofensivo"],
            "volante": ["volante", "meia central"], "lateral": ["lateral"], "zagueiro": ["zagueiro"], "goleiro": ["goleiro"]}
    # Atuação híbrida: compara com a união controlada dos setores que tiveram participação relevante.
    roles = {r for r, share in (role_mix or {}).items() if r in near and float(share) >= 0.20}
    if len(roles) > 1:
        candidates = set(roles)
        for role in roles:
            candidates.update(near.get(role, [role]))
        g = ref[ref["funcao"].isin(candidates)]
    else:
        g = ref[ref["funcao"] == funcao]
    if len(g) < 12:                                  # poucos pares: amplia para funções vizinhas
        candidates = set(near.get(funcao, [funcao]))
        for role in roles:
            candidates.update(near.get(role, [role]))
        g = ref[ref["funcao"].isin(candidates)]
    return g


def _pct(v, series: pd.Series) -> Optional[float]:
    if v is None or pd.isna(v):
        return None
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 5:
        return None
    return 100.0 * ((s < v).sum() + 0.5 * (s == v).sum()) / len(s)


def _score(v, series: pd.Series, higher: bool) -> Optional[float]:
    pct = _pct(v, series)
    return None if pct is None else pct_to_score(pct if higher else 100 - pct)


# ------------------------------------------------------------------ nota
def evaluate(row: Dict[str, Any], ref: pd.DataFrame, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Desempenho, impacto e confiança de UMA atuação, com as dimensões e a base de cada uma."""
    funcao = row.get("funcao") or role_of(row.get("posicao"))
    mins = max(0.0, _as_float(row.get("minutos")))
    role_mix = row.get("role_mix")
    peers = _peer_group(ref, funcao, role_mix)
    gk = funcao == "goleiro"
    inds, dims, base_wts = (GK_INDICATORS, GK_DIMS, GK_WEIGHTS) if gk else (
        INDICATORS, DIMS, WEIGHTS.get(funcao, WEIGHTS["meia central"])
    )
    wts = list(base_wts)
    if not gk and isinstance(role_mix, dict) and role_mix:
        mix = {str(k): max(_as_float(v), 0.0) for k, v in role_mix.items() if k in WEIGHTS}
        total_mix = sum(mix.values())
        if total_mix > 0:
            wts = [
                sum(WEIGHTS[role][i] * share for role, share in
                    ((role, weight / total_mix) for role, weight in mix.items()))
                for i in range(len(DIMS))
            ]
    acc: Dict[str, List[tuple]] = {k: [] for k in dims}
    detail = []
    for k, (dim, w, hi) in inds.items():
        pc = _pct(row.get(k), peers[k] if k in peers else pd.Series(dtype=float))
        sc = None if pc is None else pct_to_score(pc if hi else 100 - pc)
        if sc is not None:
            acc[dim].append((sc, w))
            ref_med = pd.to_numeric(peers[k], errors="coerce").median() if k in peers else None
            detail.append({"indicador": k, "rotulo": IND_PT.get(k, k), "dimensao": dim, "valor": row.get(k),
                           "nota": round(sc, 1), "percentil": round(pc if hi else 100 - pc), "mediana_pares": ref_med,
                           "maior_melhor": hi})
    dim_score = {k: (sum(s * w for s, w in v) / sum(w for _, w in v)) if v else None for k, v in acc.items()}
    if not gk:
        # disciplina: expulsão é penalização severa (consequência independente — não é dupla contagem)
        if _as_float(row.get("vermelhos")) > 0:
            dim_score["disciplina"] = min(dim_score["disciplina"] if dim_score["disciplina"] is not None else REF_SCORE, 1.0)
    obs = [(dim_score[k], w) for k, w in zip(dims, wts) if dim_score[k] is not None]
    raw = sum(s * w for s, w in obs) / sum(w for _, w in obs) if obs else None
    cover = sum(w for _, w in obs) / 100.0 if obs else 0.0
    c_min = min(1.0, max(0.0, mins / 60.0))
    c_pool = min(1.0, len(peers) / 40.0)
    conf = round(100 * (0.35 * c_min + 0.35 * cover + 0.30 * c_pool))
    if mins < 15 or raw is None:
        perf = None
    else:
        perf = round(float(np.clip(c_min * raw + (1 - c_min) * REF_SCORE, 0, 10)), 1)
        if perf >= 9.6 and (cover < 0.85 or mins < 75):
            perf = 9.5                               # 10 exige atuação completa e bem observada
    delta = impact_delta(row, context) if perf is not None else None
    nota = round(float(np.clip(perf + delta, 0, 10)), 1) if perf is not None else None
    return {"jogador": row.get("jogador"), "equipe": row.get("equipe"), "funcao": funcao, "minutos": mins,
            "desempenho": perf, "nota": nota, "nota_final": nota, "classificacao": label(nota),
            "impacto": (round(delta, 1) if delta is not None else None),
            "confianca_pct": conf, "confianca": "alta" if conf >= 75 else "média" if conf >= 50 else "baixa",
            "amostra": minutes_tier(mins), "dimensoes": {k: (round(v, 1) if v is not None else None) for k, v in dim_score.items()},
            "dimensoes_pt": DIM_PT if not gk else GK_DIM_PT, "pesos": dict(zip(dims, wts)), "base": detail,
            "role_mix": (dict(role_mix) if isinstance(role_mix, dict) else {}),
            "eventos_decisivos": {
                "gols": int(_as_float(row.get("gols"))), "assistencias": int(_as_float(row.get("assistencias"))),
                "gols_decisivos": int(_as_float((context or {}).get("gols_decisivos"))),
                "penaltis_defendidos_disputa": int(_as_float(row.get("shootout_saves"))),
                "defesas_chave": int(_as_float(row.get("key_saves"))),
                "penaltis_convertidos_disputa": int(_as_float(row.get("shootout_penaltis_marcados"))),
                "penaltis_perdidos_disputa": int(_as_float(row.get("shootout_penaltis_perdidos"))),
                "grandes_chances_desperdicadas": int(_as_float(row.get("chances_claras_perdidas"))),
                "erros_que_geraram_chance": int(_as_float(row.get("erros_que_viraram_chance"))),
                "expulsoes": int(_as_float(row.get("vermelhos"))),
            },
            "pares": int(len(peers))}


def impact_delta(row: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> float:
    """Ajuste decisivo em pontos (não é uma segunda nota). Intervalo limitado a −1,5…+2,5."""
    ctx = context or {}
    total_goals = max(_as_float(row.get("gols")), 0.0)
    raw_penalties = row.get("gols_penalti")
    if raw_penalties is None or pd.isna(raw_penalties):
        # Fontes de boxscore podem não separar pênaltis de bola rolando: usa-se peso intermediário,
        # sem fingir que a distinção foi observada.
        goal_bonus = 0.42 * total_goals
    else:
        penalty_goals = min(max(_as_float(raw_penalties), 0.0), total_goals)
        open_goals = max(total_goals - penalty_goals, 0.0)
        goal_bonus = 0.48 * open_goals + 0.30 * penalty_goals
    bonus = min(1.45, goal_bonus)
    bonus += min(0.70, 0.35 * _as_float(row.get("assistencias")))
    bonus += min(0.40, 0.20 * _as_float(ctx.get("gols_decisivos")))
    # Defesas de pênalti na disputa e defesas de chances claras em momento de alta alavancagem.
    if row.get("funcao") == "goleiro":
        bonus += min(1.50, 0.90 * _as_float(row.get("shootout_saves")))
        bonus += min(0.90, 0.65 * _as_float(row.get("key_saves")))
        # Em fontes sem xGOT, gols evitados pode ser um proxy baseado em xG pré-chute.
        prevented = max(_as_float(row.get("gols_evitados")), 0.0)
        bonus += min(0.45, 0.25 * prevented)
    bonus += min(0.30, 0.10 * _as_float(row.get("shootout_penaltis_marcados")))
    bonus -= min(0.70, 0.35 * _as_float(row.get("shootout_penaltis_perdidos")))
    bonus -= min(0.90, 0.45 * _as_float(row.get("chances_claras_perdidas")))
    bonus -= 0.80 * _as_float(row.get("erros_que_viraram_chance"))
    bonus -= 0.60 * _as_float(row.get("vermelhos"))
    return round(float(np.clip(bonus, -1.5, 2.5)), 1)


def impact(row: Dict[str, Any], perf: Optional[float], context: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """Compatibilidade: devolve a nota final (desempenho-base + ajuste decisivo)."""
    if perf is None:
        return None
    return round(float(np.clip(perf + impact_delta(row, context), 0, 10)), 1)


def match_ratings_v2(df: pd.DataFrame, extra_ref: bool = True) -> pd.DataFrame:
    """Avaliação 3.0 de todos os jogadores de uma partida com lances (a própria partida entra na referência)."""
    ind = indicators(df)
    if ind.empty:
        return ind
    ref = reference_pool([ind] if extra_ref else None)
    from src.metrics.match_facts import goals

    decisive = _decisive_goals(goals(df))
    rows = []
    for r in ind.to_dict("records"):
        ev = evaluate(r, ref, {"gols_decisivos": decisive.get(r["jogador"], 0)})
        rows.append({**{k: r.get(k) for k in ("jogador", "equipe", "posicao", "funcao", "minutos", "gols", "assistencias",
                                              "xg", "xa", "defesas", "gols_sofridos", "gols_evitados",
                                              "key_saves", "shootout_saves", "shootout_penaltis_marcados",
                                              "shootout_penaltis_perdidos", "role_mix")},
                     "desempenho": ev["desempenho"], "impacto": ev["impacto"], "nota": ev["nota"],
                     "nota_final": ev["nota_final"], "confianca": ev["confianca"],
                     "confianca_pct": ev["confianca_pct"], "classificacao": ev["classificacao"], "amostra": ev["amostra"],
                     **{f"dim_{k}": v for k, v in ev["dimensoes"].items()}, "_detalhe": ev})
    return pd.DataFrame(rows).sort_values(["nota"], ascending=False, na_position="last").reset_index(drop=True)


def _decisive_goals(gl: List[Dict[str, Any]]) -> Dict[str, int]:
    """Gols que empataram ou viraram o placar naquele momento (contexto, não bônus automático de 'final')."""
    score: Dict[str, int] = {}
    out: Dict[str, int] = {}
    for g in sorted(gl, key=lambda x: (x.get("minuto") or 0)):
        team = g["equipe"]
        before = dict(score)
        score[team] = score.get(team, 0) + 1
        mine, other = before.get(team, 0), max([v for k, v in before.items() if k != team] or [0])
        # Só marca quando empata ou passa à frente; gol que apenas diminui uma desvantagem não vira "decisivo".
        if mine <= other and mine + 1 >= other and not g.get("gol_contra"):
            out[g["jogador"]] = out.get(g["jogador"], 0) + 1
    return out


def report(ev: Dict[str, Any]) -> str:
    """Relatório explicável de uma atuação, incluindo o ajuste decisivo e as lacunas de observação."""
    if ev.get("desempenho") is None:
        return (f"**{ev['jogador']}** jogou {ev['minutos']:.0f} min — {ev['amostra']}: sem nota (pouco tempo ou sem lances "
                "suficientes). Ausência de dado não vira nota baixa.")
    dims = {k: v for k, v in ev["dimensoes"].items() if v is not None}
    pt = ev["dimensoes_pt"]
    top = sorted(dims.items(), key=lambda kv: -kv[1])[:2]
    low = sorted(dims.items(), key=lambda kv: kv[1])[:2]
    not_obs = [pt[k] for k, v in ev["dimensoes"].items() if v is None]
    delta = float(ev.get("impacto") or 0)
    sign = "+" if delta > 0 else ""
    s = (f"**{ev['jogador']}** ({ev['funcao']}, {ev['minutos']:.0f} min): nota final **{ev['nota']:.1f}** "
         f"({ev['classificacao']}); desempenho-base **{ev['desempenho']:.1f}**; ajuste decisivo **{sign}{delta:.1f} pts**; "
         f"confiança {ev['confianca']} ({ev['confianca_pct']}%). "
         f"Melhor em {pt[top[0][0]].lower()} ({top[0][1]:.1f})"
         + (f" e {pt[top[1][0]].lower()} ({top[1][1]:.1f})" if len(top) > 1 else "")
         + f"; menor dimensão observada: {pt[low[0][0]].lower()} ({low[0][1]:.1f}).")
    events = ev.get("eventos_decisivos") or {}
    moments = []
    if events.get("penaltis_defendidos_disputa"):
        moments.append(f"{events['penaltis_defendidos_disputa']} pênalti(s) defendido(s) na disputa")
    if events.get("defesas_chave"):
        moments.append(f"{events['defesas_chave']} defesa(s) de alto impacto")
    if events.get("gols_decisivos"):
        moments.append(f"{events['gols_decisivos']} gol(s) que empatou(aram) ou virou(aram) o placar")
    if events.get("grandes_chances_desperdicadas"):
        moments.append(f"{events['grandes_chances_desperdicadas']} grande(s) chance(s) desperdiçada(s)")
    if moments:
        s += " Momentos decisivos contabilizados: " + "; ".join(moments) + "."
    if len(ev.get("role_mix") or {}) > 1:
        roles = ", ".join(f"{role} {share:.0%}" for role, share in ev["role_mix"].items())
        s += " Papéis detectados nos eventos: " + roles + " (aproximação pelas posições anotadas, não tracking)."
    if not_obs:
        s += " Não observado nesta fonte: " + ", ".join(x.lower() for x in not_obs) + "."
    s += f" Comparado com {ev['pares']} atuações de jogadores da mesma função ou de papéis próximos na base."
    return s


def build_reference_from_db(limit: int = 300, progress=None) -> int:
    """
    Monta a base de referência dos percentis com até `limit` partidas COM LANCES do banco (StatsBomb, Wyscout, OpenPlay):
        python -m src.analytics.rating_v2 --referencia 300
    Quanto mais partidas, mais justa a comparação por função. Roda uma vez (e de novo quando a base crescer).
    """
    from src.data_hub.service import MatchDataService
    from src.metrics.xt_model import ExpectedThreatModel
    from src.preprocessing.event_cleaner import EventPreprocessor

    say = progress or (lambda m: print(m, flush=True))
    svc = MatchDataService()
    with svc.db.connect() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT e.match_id FROM events e "
            "JOIN matches m ON m.match_id = e.match_id "
            "WHERE m.data_level = 'EVENTS' "
            "ORDER BY m.match_date DESC LIMIT ?",
            (int(limit),),
        )]
    dfs = []
    for i, mid in enumerate(ids, 1):
        try:
            raw = svc.db.load_events(int(mid))
            if raw is None or raw.empty:
                continue
            dfs.append(ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(raw)))
        except Exception as exc:
            say(f"  partida {mid}: {exc}")
        if i % 25 == 0:
            say(f"  {i}/{len(ids)} partidas")
    n = build_reference(dfs)
    say(f"referência da nota 3.0: {n} atuações de {len(dfs)} partidas")
    return n


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Base de referência (percentis por função) da nota 3.0.")
    ap.add_argument("--referencia", type=int, default=300, help="quantas partidas com lances usar")
    build_reference_from_db(ap.parse_args().referencia)
