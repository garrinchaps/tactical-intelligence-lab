"""
Rodada 25 — TIL Player Rating (motor v2 da nota 0–100), pedido do usuário depois da lista "Benzema 93, Dovbyk 92".

O que mudou em relação à régua antiga (src/scout/overall.py, rodadas 20–24):
  * VALOR DE MERCADO = 0% da nota (fica só para mercado/custo-benefício). Fama também 0%.
  * Nota da FotMob ≤ 5% (entra só na parte de consistência).
  * A nota nasce de 9 ATRIBUTOS medidos (1–100), cada um percentil dentro da família de posição:
      SHO finalização · CRE criação · DRI drible/condução · PAS construção · DEF defesa · PHY físico/duelos ·
      AIR jogo aéreo · SEC segurança · MOB participação/mobilidade (proxy — NÃO é velocidade medida)
    goleiro: DEFESAS · SAÍDA DE BOLA · SEGURANÇA.
  * Pesos POR POSIÇÃO (volante: defesa 30%, físico 20%, passe 20%…; centroavante: finalização 30%…). Volante marcador
    não perde nota por não criar.
  * OVR bruto = 0,75·W (média ponderada da posição) + 0,15·E (excelência: os 2 melhores atributos importantes)
    + 0,10·C (consistência: minutos do ano e nota FotMob) + polivalência (+0,5 a +1,5) − deficiência relevante.
  * Números por 90 com peso no tempo (último ano 1 · 1–2 anos 0,6 · 2–5 anos 0,25 por minuto; `*_p90w`).
  * Amostra pequena puxa para o meio (minutos ponderados / (minutos + 450)) e baixa a CONFIANÇA — 160 minutos não
    viram 93.
  * Dificuldade: nível do clube/liga + força média dos adversários enfrentados → ajuste limitado (−8 a +5 pontos de
    atributo), porque o percentil é contra jogadores de TODAS as ligas (sem isso, quem domina uma liga fraca lidera).
  * Estilos: percentuais de compatibilidade com perfis da posição (destruidor, organizador, box-to-box, lateral
    ofensivo/equilibrado/defensivo, ponta driblador/finalizador/criador, centroavante finalizador/pivô/móvel…).

A escala final (quantos 90+, 85+, 80+) continua a da escada global de overall.py e a calibração pelos jogadores de
referência do usuário corrige vieses sistemáticos (idade, nível, minutos, posição) — corrige a ESCALA, não força nomes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ATTR_KEYS = ["SHO", "CRE", "DRI", "PAS", "DEF", "PHY", "AIR", "SEC", "MOB"]
ATTR_PT = {"SHO": "Finalização", "CRE": "Criação", "DRI": "Drible e condução", "PAS": "Construção e passe",
           "DEF": "Defesa", "PHY": "Físico e duelos", "AIR": "Jogo aéreo", "SEC": "Segurança", "MOB": "Participação",
           "GKS": "Defesas", "GKD": "Saída de bola", "GKE": "Segurança (goleiro)"}

# atributo → [(métrica, peso, maior_é_melhor)]. Métrica procurada primeiro com sufixo "w" (peso no tempo).
METRICS: Dict[str, List[Tuple[str, float, bool]]] = {
    "SHO": [("goals_p90", .20, True), ("xg_p90", .22, True), ("_conv", .14, True), ("shot_acc_pct", .12, True),
            ("shots_on_target_p90", .14, True), ("shots_p90", .10, True), ("touches_opp_box_p90", .08, True)],
    "CRE": [("xa_p90", .26, True), ("chances_created_p90", .26, True), ("assists_p90", .12, True),
            ("final_third_passes_p90", .14, True), ("crosses_acc_p90", .10, True), ("line_breaking_p90", .06, True),
            ("touches_opp_box_p90", .06, True)],
    "DRI": [("dribbles_p90", .34, True), ("dribble_pct", .24, True), ("was_fouled_p90", .14, True),
            ("dispossessed_p90", .14, False), ("touches_opp_box_p90", .14, True)],
    "PAS": [("line_breaking_p90", .24, True), ("final_third_passes_p90", .20, True), ("long_balls_p90", .14, True),
            ("long_ball_pct", .10, True), ("pass_rate_pct", .14, True), ("passes_acc_p90", .12, True),
            ("xa_p90", .06, True)],
    "DEF": [("tackles_p90", .20, True), ("interceptions_p90", .22, True), ("recoveries_p90", .15, True),
            ("def_actions_p90", .12, True), ("duel_rate_pct", .12, True), ("clearances_p90", .08, True),
            ("dribbled_past_p90", .11, False)],
    "PHY": [("duel_rate_pct", .30, True), ("duel_won_p90", .26, True), ("aerials_won_p90", .14, True),
            ("was_fouled_p90", .10, True), ("recoveries_p90", .10, True), ("dispossessed_p90", .10, False)],
    "AIR": [("aerials_won_p90", .45, True), ("aerial_pct", .40, True), ("clearances_p90", .15, True)],
    "SEC": [("dispossessed_p90", .34, False), ("errors_p90", .30, False), ("fouls_p90", .14, False),
            ("pass_rate_pct", .12, True), ("_cards_p90", .10, False)],
    "MOB": [("touches_p90", .34, True), ("recoveries_p90", .20, True), ("dribbles_p90", .14, True),
            ("sprints_p90", .16, True), ("def_actions_p90", .16, True)],
    # goleiro
    "GKS": [("saves_p90", .45, True), ("_save_ratio", .55, True)],
    "GKD": [("long_ball_pct", .45, True), ("pass_rate_pct", .35, True), ("long_balls_p90", .20, True)],
    "GKE": [("errors_p90", .70, False), ("_cards_p90", .30, False)],
}

FAMILY_OF = {"GK": "GK", "CB": "CB", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "DM": "DM", "CM": "CM",
             "AM": "AM", "LM": "WIDE", "RM": "WIDE", "LW": "WIDE", "RW": "WIDE", "ST": "ST", "CF": "ST"}
POOL_OF = {"GK": "GK", "CB": "CB", "FB": "FB", "DM": "MID", "CM": "MID", "AM": "AM", "WIDE": "WIDE", "ST": "ST"}

POS_WEIGHTS: Dict[str, Dict[str, float]] = {
    "ST": {"SHO": .30, "CRE": .10, "DRI": .10, "PAS": .10, "DEF": .03, "PHY": .15, "AIR": .12, "SEC": .05, "MOB": .05},
    "WIDE": {"SHO": .20, "CRE": .20, "DRI": .25, "PAS": .12, "DEF": .03, "PHY": .10, "AIR": .03, "SEC": .02, "MOB": .05},
    "AM": {"SHO": .15, "CRE": .25, "DRI": .15, "PAS": .25, "DEF": .03, "PHY": .07, "AIR": .02, "SEC": .05, "MOB": .03},
    "CM": {"SHO": .08, "CRE": .15, "DRI": .10, "PAS": .25, "DEF": .15, "PHY": .15, "AIR": .05, "SEC": .05, "MOB": .02},
    "DM": {"SHO": .02, "CRE": .08, "DRI": .05, "PAS": .20, "DEF": .30, "PHY": .20, "AIR": .08, "SEC": .05, "MOB": .02},
    "FB": {"SHO": .05, "CRE": .12, "DRI": .12, "PAS": .18, "DEF": .25, "PHY": .15, "AIR": .05, "SEC": .05, "MOB": .03},
    "CB": {"SHO": .01, "CRE": .02, "DRI": .03, "PAS": .18, "DEF": .35, "PHY": .20, "AIR": .15, "SEC": .05, "MOB": .01},
    "GK": {"GKS": .75, "GKD": .10, "GKE": .15},
}

# perfis por família: nome → (atributos que definem, frase)
STYLES: Dict[str, Dict[str, Tuple[List[str], str]]] = {
    "DM": {"Destruidor": (["DEF", "PHY"], "desarma, ganha duelos e recupera"),
           "Organizador (regista)": (["PAS", "SEC"], "distribui, segura a bola e dita o ritmo"),
           "Box-to-box": (["PHY", "MOB", "CRE"], "cobre o campo, chega e participa nas duas áreas"),
           "Interceptor": (["DEF", "SEC"], "lê o passe e corta a linha"),
           "Combate (estilo Gattuso)": (["PHY", "DEF", "MOB"], "pressão, duelo e recuperação")},
    "CM": {"Box-to-box": (["PHY", "MOB", "SHO"], "chega à área e volta para defender"),
           "Organizador": (["PAS", "SEC"], "controla a posse e o ritmo"),
           "Meia vertical": (["PAS", "CRE", "DRI"], "progride com passe e condução"),
           "Meia de pressão": (["DEF", "MOB"], "recupera alto e intensifica")},
    "AM": {"Criador": (["CRE", "PAS"], "passe decisivo e chances criadas"),
           "Meia finalizador": (["SHO", "MOB"], "chega para concluir"),
           "Meia de condução": (["DRI", "CRE"], "carrega a bola e desequilibra"),
           "Meia de pressão": (["DEF", "MOB"], "pressiona a saída do rival")},
    "WIDE": {"Driblador": (["DRI", "MOB"], "parte para cima no 1×1"),
             "Finalizador": (["SHO"], "ataca o gol"),
             "Criador": (["CRE", "PAS"], "serve os companheiros"),
             "Ponta completo": (["SHO", "CRE", "DRI"], "faz de tudo no ataque")},
    "ST": {"Finalizador": (["SHO"], "vive para o gol"),
           "Pivô": (["PHY", "AIR", "PAS"], "segura de costas e distribui"),
           "Atacante móvel": (["DRI", "MOB", "CRE"], "sai da área e participa"),
           "Centroavante aéreo": (["AIR", "SHO"], "ganha por cima"),
           # rodada 27: quem marca muito atacando o espaço e as costas (Kaio Jorge) não é pivô nem só finalizador
           "Atacante de ruptura": (["SHO", "DRI", "PHY"], "ataca o espaço e as costas da defesa em velocidade"),
           "Completo": (["SHO", "CRE", "PAS"], "marca e cria")},
    "FB": {"Lateral ofensivo": (["CRE", "DRI", "MOB"], "apoia, cruza e dribla"),
           "Lateral equilibrado": (["DEF", "PAS", "CRE"], "defende e constrói"),
           "Lateral defensivo": (["DEF", "PHY", "SEC"], "marca primeiro"),
           "Lateral construtor": (["PAS", "SEC"], "sai jogando por dentro")},
    "CB": {"Zagueiro dominante": (["AIR", "PHY", "DEF"], "ganha pelo alto e no corpo"),
           "Zagueiro de antecipação": (["DEF", "SEC"], "corta antes de a bola chegar"),
           "Zagueiro construtor": (["PAS", "SEC"], "quebra linhas com passe")},
    "GK": {"Goleiro de defesas": (["GKS"], "segura chutes"),
           "Goleiro com os pés": (["GKD"], "participa da saída de bola")},
}

SHRINK_MIN = 450.0


def _num(u: pd.DataFrame, col: str) -> pd.Series:
    for c in (f"{col}w", f"{col}_w", col):
        if c in u:
            s = pd.to_numeric(u[c], errors="coerce")
            if s.notna().any():
                return s
    return pd.Series(np.nan, index=u.index, dtype=float)


def derived(u: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(index=u.index)
    goals, shots = _num(u, "goals_p90"), _num(u, "shots_p90")
    d["_conv"] = (goals / shots.where(shots >= .8)).clip(0, 1)
    d["_cards_p90"] = _num(u, "yellow_cards_p90").fillna(0) + 2 * _num(u, "red_cards_p90").fillna(0) \
        if "yellow_cards_p90" in u else np.nan
    saves, xgot = _num(u, "saves_p90"), _num(u, "xgot_faced_p90")
    d["_save_ratio"] = (saves / xgot.where(xgot >= .5)).clip(0, 3)
    return d


def family(u: pd.DataFrame) -> pd.Series:
    role = u["papel"] if "papel" in u else pd.Series("", index=u.index)
    return role.astype(str).str.upper().map(FAMILY_OF).fillna("")


def attributes(u: pd.DataFrame) -> pd.DataFrame:
    """Atributos 1–100 (percentil na família, puxado para 50 pela amostra, com ajuste de dificuldade)."""
    out = pd.DataFrame(index=u.index)
    fam = family(u)
    pool = fam.map(POOL_OF).fillna("")
    extra = derived(u)
    mins = _num(u, "minutos_ponderados")
    mins = mins.fillna(pd.to_numeric(u.get("minutos_12m"), errors="coerce")).fillna(
        pd.to_numeric(u.get("minutos"), errors="coerce")).fillna(0)
    elig = mins >= 90
    r = mins / (mins + SHRINK_MIN)
    lvl = pd.to_numeric(u.get("_lvl"), errors="coerce") if "_lvl" in u else pd.Series(np.nan, index=u.index)
    lvl = lvl.fillna(pd.to_numeric(u.get("nivel_competicao_principal"), errors="coerce")).fillna(.5).clip(0, 1)
    opp = pd.to_numeric(u.get("nivel_adversario_12m", u.get("nivel_adversario_medio")), errors="coerce") \
        if ("nivel_adversario_12m" in u or "nivel_adversario_medio" in u) else pd.Series(np.nan, index=u.index)
    opp_n = ((opp.fillna(50) - 50) / 25).clip(-1, 1)
    delta = (28 * (lvl - .62) * .75 + 5 * opp_n * .25).clip(-8, 5)
    out["dificuldade_ajuste"] = delta.round(1)
    for attr, parts in METRICS.items():
        num = pd.Series(0.0, index=u.index)
        den = pd.Series(0.0, index=u.index)
        n_ok = pd.Series(0, index=u.index)
        for col, w, hi in parts:
            v = extra[col] if col in extra else _num(u, col)
            v = v.where(elig)
            if v.notna().sum() < 10:
                continue
            p = v.groupby(pool).rank(pct=True)
            if not hi:
                p = 1 - p
            ok = p.notna()
            num[ok] += w * p[ok]
            den[ok] += w
            n_ok[ok] += 1
        pct = (num / den.replace(0, np.nan)).where(n_ok >= (1 if attr.startswith("GK") else 2))
        score = 1 + 99 * pct
        perf_attr = attr not in ("SEC", "MOB", "GKE")
        if perf_attr:
            score = score + delta
        score = 50 + (score - 50) * r
        out[attr] = score.clip(1, 99).round(0).where(pct.notna())
    gk = fam.eq("GK")
    for a in ATTR_KEYS:
        out.loc[gk, a] = np.nan
    for a in ("GKS", "GKD", "GKE"):
        out.loc[~gk, a] = np.nan
    out["_fam2"] = fam
    out["_r"] = r
    out["minutos_ponderados_"] = mins
    return out


def raw_overall(u: pd.DataFrame, A: pd.DataFrame) -> pd.DataFrame:
    """W, E, C, polivalência e deficiência → nota bruta (antes da escala global)."""
    fam = A["_fam2"]
    res = pd.DataFrame(index=u.index)
    T = pd.to_numeric(u.get("rating_12m"), errors="coerce") if "rating_12m" in u else pd.Series(np.nan, index=u.index)
    t_pct = T.groupby(fam.map(POOL_OF).fillna("")).rank(pct=True) * 100
    m12 = pd.to_numeric(u.get("minutos_12m"), errors="coerce").fillna(0)
    prev = _num(u, "minutos_temporada_anterior").fillna(0)
    avail = (pd.concat([m12, .6 * prev], axis=1).max(axis=1) / 2700).clip(0, 1) * 100
    W, E, Bp, Pd, n_strong = [], [], [], [], []
    for i in u.index:
        f = fam.at[i]
        w = POS_WEIGHTS.get(f)
        if not w:
            W.append(np.nan); E.append(np.nan); Bp.append(0.0); Pd.append(0.0); n_strong.append(0)
            continue
        vals = {a: A.at[i, a] for a in w if a in A and pd.notna(A.at[i, a])}
        cover = sum(w[a] for a in vals)
        if cover < .45:
            W.append(np.nan); E.append(np.nan); Bp.append(0.0); Pd.append(0.0); n_strong.append(0)
            continue
        W.append(sum(w[a] * vals[a] for a in vals) / cover)
        imp = sorted((vals[a] for a in vals if w[a] >= .08), reverse=True)
        E.append(float(np.mean(imp[:2])) if imp else np.nan)
        strong = sum(1 for a in vals if w[a] >= .05 and vals[a] >= 80)
        n_strong.append(strong)
        crit = [a for a in vals if w[a] >= .15 and vals[a] <= 30]
        pd_ = min(4.0, sum((30 - vals[a]) / 8 for a in crit)) * float(A.at[i, "_r"] >= .5)
        bp = 0.0 if crit else (1.5 if strong >= 5 else 1.0 if strong == 4 else .5 if strong == 3 else 0.0)
        Bp.append(bp)
        Pd.append(pd_)
    res["W"], res["E"] = W, E
    res["C"] = (.5 * t_pct.fillna(50) + .5 * avail)
    res["bonus_polivalencia"], res["penal_deficiencia"] = Bp, Pd
    res["atributos_fortes"] = n_strong
    res["bruto"] = .75 * res["W"] + .15 * res["E"].fillna(res["W"]) + .10 * res["C"] + res["bonus_polivalencia"] \
        - res["penal_deficiencia"]
    r = A["_r"]
    res["confianca_nota"] = (100 * (.75 * r + .25 * (res["W"].notna()).astype(float))).round(0).where(res["W"].notna())
    return res


def styles(A: pd.DataFrame) -> pd.Series:
    """Perfis com % de compatibilidade (os 3 maiores). Ex.: 'Destruidor 78% · Box-to-box 61% · Organizador 44%'."""
    out = []
    for i in A.index:
        f = A.at[i, "_fam2"]
        defs = STYLES.get(f) or {}
        sc = []
        for name, (keys, _txt) in defs.items():
            v = [A.at[i, k] for k in keys if k in A and pd.notna(A.at[i, k])]
            if len(v) >= max(1, len(keys) - 1):
                sc.append((float(np.mean(v)), name))
        sc.sort(reverse=True)
        out.append(" · ".join(f"{n} {s:.0f}%" for s, n in sc[:3]) if sc else "")
    return pd.Series(out, index=A.index)


def compute(u: pd.DataFrame) -> pd.DataFrame:
    """Todas as colunas do motor: atributos (atr2_*), W/E/C, bônus, penalidade, bruto, confiança e estilo."""
    A = attributes(u)
    R = raw_overall(u, A)
    out = pd.DataFrame(index=u.index)
    for a in ATTR_KEYS + ["GKS", "GKD", "GKE"]:
        out[f"atr2_{a}"] = A[a]
    out["dificuldade_ajuste"] = A["dificuldade_ajuste"]
    for c in ("W", "E", "C", "bonus_polivalencia", "penal_deficiencia", "atributos_fortes", "bruto", "confianca_nota"):
        out[f"ovr2_{c}" if c not in ("confianca_nota",) else c] = R[c]
    out["estilo"] = styles(A)
    return out
