"""
Rodada 22 — POTENCIAL 0–100 (mesma escala do overall), ao lado do overall em todo o Scout.

Pedido do usuário: "um cálculo perfeito de potencial para todos os jogadores… idade, qualidade, projeção, valor de
mercado, números, prospecto físico, média das notas, minutagem comparada à qualidade do time… ações com a bola por jogo
(importa muito)… cada um com peso maior por posição". Honestidade: potencial é PROJEÇÃO, não fato. Cada atleta recebe:

  potencial = overall de hoje + espaço de crescimento pela IDADE × multiplicador de TALENTO

* Espaço pela idade (pontos de overall que um jogador típico ainda ganha): 16 anos ≈ 16 · 19 ≈ 12 · 21 ≈ 8 · 23 ≈ 4,5 ·
  25 ≈ 2 · 27+ ≈ 0 (é o mesmo formato de curva de crescimento usado em jogos de futebol e na literatura de pico ~26–28).
* Talento (0–100) = média ponderada dos sinais que EXISTEM para o atleta (o que falta não vira zero; só sai da média):
    - produção na função (índice por 90 com pesos por posição — ver POS_WEIGHTS) contra TODOS da mesma posição;
    - nota média FotMob dos últimos 12 meses ajustada pelo nível da liga;
    - minutos no ano × nível do time/liga ("jogar muito num time forte cedo" é o sinal mais forte de talento);
    - valor de mercado contra quem tem a MESMA idade e posição (o mercado já embute projeção);
    - ações com a bola por 90 (toques) contra a posição;
    - seleção de base (jogos em Mundial/Sul-Americano/Euro de base; mais peso para quem é titular frequente);
    - prospecto físico onde ele importa (altura para zagueiro, goleiro e centroavante) — só com altura cadastrada;
    - precocidade (valor e minutos contra a mesma idade, já calculada no Scout).
* Multiplicador = 0,3 + 0,85 × (talento/100)^1,2 → talento 20 ≈ 0,42 · 50 ≈ 0,67 · 80 ≈ 0,95 · 95 ≈ 1,1; acima de 80
  de overall o espaço encolhe (crescer perto do topo é mais difícil). Ex.: 18 anos, overall 77, talento 80 → ~89.
* Confiança: minutos + quantos sinais existem. Explicação: os 3 sinais que mais puxaram para cima e o que mais limitou.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

AGE_GROWTH = {15: 17.0, 16: 16.0, 17: 14.5, 18: 13.0, 19: 11.5, 20: 10.0, 21: 8.0, 22: 6.0, 23: 4.5, 24: 3.0, 25: 2.0,
              26: 1.2, 27: .6}
POT_CAP = 95.0

# pesos por posição (família do overall). Negativo = quanto MENOS, melhor (perdas de bola, vezes driblado, erros).
POS_WEIGHTS: Dict[str, Dict[str, float]] = {
    "ST": {"goals_p90": 1.2, "xg_p90": 1.0, "shot_acc_pct": .6, "touches_opp_box_p90": .8, "touches_p90": .6,
           "assists_p90": .4, "dribble_pct": .3, "aerial_pct": .4, "duels_won_pct": .4},
    "WIDE": {"dribbles_p90": 1.0, "dribble_pct": .5, "chances_created_p90": .9, "xa_p90": .8, "goals_p90": .7,
             "xg_p90": .5, "touches_p90": .8, "cross_pct": .3, "dispossessed_p90": -.4},
    "AM": {"chances_created_p90": 1.1, "xa_p90": 1.0, "final_third_passes_p90": .8, "touches_p90": .9,
           "dribbles_p90": .6, "goals_p90": .6, "pass_accuracy_pct": .4, "dispossessed_p90": -.4},
    "MID": {"touches_p90": 1.0, "pass_accuracy_pct": .8, "line_breaking_p90": .8, "recoveries_p90": .7,
            "interceptions_p90": .6, "tackles_p90": .6, "duels_won_pct": .6, "final_third_passes_p90": .5,
            "dispossessed_p90": -.4},
    "CB": {"aerial_pct": 1.0, "duels_won_pct": .9, "interceptions_p90": .7, "clearances_p90": .5,
           "pass_accuracy_pct": .6, "long_ball_pct": .5, "line_breaking_p90": .5, "dribbled_past_p90": -.7,
           "errors_p90": -.6},
    "FB": {"crosses_acc_p90": .7, "chances_created_p90": .7, "tackles_p90": .7, "interceptions_p90": .6,
           "duels_won_pct": .7, "dribbles_p90": .4, "touches_p90": .6, "dribbled_past_p90": -.6},
    "GK": {"saves_p90": .6, "pass_accuracy_pct": .4, "long_ball_pct": .3},
}
SIGNAL_WEIGHTS = {"producao": 1.3, "nota": 1.0, "minutos_nivel": 1.4, "valor_idade": 1.1, "toques": .8,
                  "base": .7, "fisico": .4, "precocidade": .6}
SIGNAL_LABELS = {"producao": "produção na função", "nota": "nota média (ajustada pela liga)",
                 "minutos_nivel": "minutos no ano × nível do time", "valor_idade": "valor de mercado para a idade",
                 "toques": "ações com a bola por 90", "base": "seleção de base", "fisico": "prospecto físico",
                 "precocidade": "precocidade"}
TALL_MATTERS = {"CB": 186.0, "GK": 188.0, "ST": 183.0}      # mediana aproximada de quem joga na posição


def _col(u: pd.DataFrame, name: str) -> pd.Series:
    if name in u:
        return pd.to_numeric(u[name], errors="coerce")
    return pd.Series(np.nan, index=u.index, dtype=float)


def age_growth(age: pd.Series) -> pd.Series:
    a = pd.to_numeric(age, errors="coerce")
    xs = sorted(AGE_GROWTH)
    g = np.interp(a.fillna(99).clip(15, 28).values, xs + [28], [AGE_GROWTH[x] for x in xs] + [0.0])
    return pd.Series(g, index=a.index).where(a.notna(), 0.0)


def _rank_pct(v: pd.Series, groups: pd.Series, eligible: pd.Series) -> pd.Series:
    x = v.where(eligible)
    return x.groupby(groups).rank(pct=True) * 100


def production_index(u: pd.DataFrame, fam: pd.Series, eligible: pd.Series) -> pd.Series:
    """Índice 0–100 por posição: percentil de cada número (dentro da posição) ponderado pelos pesos da posição."""
    out = pd.Series(np.nan, index=u.index)
    for f, weights in POS_WEIGHTS.items():
        idx = fam.index[fam == f]
        if not len(idx):
            continue
        num = pd.Series(0.0, index=idx)
        den = pd.Series(0.0, index=idx)
        for col, w in weights.items():
            v = _col(u, col).loc[idx].where(eligible.loc[idx])
            if v.notna().sum() < 5:
                continue
            p = v.rank(pct=True) * 100
            if w < 0:
                p = 100 - p
            ok = p.notna()
            num[ok] += abs(w) * p[ok]
            den[ok] += abs(w)
        out.loc[idx] = (num / den.replace(0, np.nan)).where(den >= 1.5)
    return out


def signals(u: pd.DataFrame, fam: pd.Series) -> pd.DataFrame:
    """Os sinais de talento (0–100) de cada atleta; NaN = sinal sem dado."""
    age = _col(u, "idade")
    m12 = _col(u, "minutos_12m")
    if m12.isna().all():
        m12 = _col(u, "minutos")
    lvl = _col(u, "_lvl").fillna(_col(u, "nivel_competicao_principal"))
    elig = m12.fillna(0) >= 450
    s = pd.DataFrame(index=u.index)
    s["producao"] = production_index(u, fam, elig)
    rating = _col(u, "rating_12m").fillna(_col(u, "rating_media"))
    s["nota"] = _rank_pct(rating + .9 * (lvl.fillna(.45) - .7), fam, elig)
    share = (m12.fillna(0) / 2700).clip(0, 1)
    mn = share * (.35 + .65 * lvl.fillna(.45).clip(0, 1))
    s["minutos_nivel"] = (mn.where(m12.notna()) * 100).clip(0, 100)
    val = _col(u, "valor_mercado_eur").where(lambda x: x > 0)
    band = pd.cut(age, [0, 18, 20, 22, 24, 27, 31, 60], labels=False)
    s["valor_idade"] = np.log1p(val).groupby([fam, band]).rank(pct=True) * 100
    s["toques"] = _rank_pct(_col(u, "touches_p90"), fam, elig)
    yj = _col(u, "selecao_base_jogos")
    ypct = _col(u, "selecao_base_pct")
    # jogos de base + (quando há nota) o quanto ele foi dos MELHORES da competição de base
    s["base"] = (35 + 8 * yj.clip(upper=5) + (.35 * (ypct - 50)).fillna(0)).clip(5, 98).where(yj > 0)
    h = _col(u, "altura_cm").where(lambda x: x.between(150, 215))
    med = fam.map(TALL_MATTERS)
    s["fisico"] = (50 + 6 * (h - med)).clip(5, 95).where(med.notna() & h.notna())
    s["precocidade"] = _col(u, "precocidade")
    return s


def compute(u: pd.DataFrame, fam: Optional[pd.Series] = None) -> pd.DataFrame:
    """Devolve colunas: potencial, potencial_crescimento, potencial_talento, potencial_confianca_pct, potencial_porque."""
    out = pd.DataFrame(index=u.index)
    if u is None or u.empty:
        return out
    if fam is None:
        from src.scout.overall import FAMILY

        fam = (u["papel"] if "papel" in u else pd.Series("", index=u.index)).map(FAMILY).fillna("")
    q = _col(u, "qualidade")
    sig = signals(u, fam)
    w = pd.Series(SIGNAL_WEIGHTS)
    have = sig.notna()
    num = (sig.fillna(0) * w).sum(axis=1)
    den = (have * w).sum(axis=1)
    talent = (num / den.replace(0, np.nan)).fillna(50.0)
    # pouca evidência puxa o talento para a média (50): não dá para chamar de joia quem quase não foi visto
    evidence = (den / w.sum()).clip(0, 1)
    talent = 50 + (talent - 50) * (.35 + .65 * evidence)
    mult = .3 + .85 * (talent / 100).clip(0, 1) ** 1.2
    # perto do topo crescer é mais difícil: acima de 80 o espaço encolhe (84 → ×0,9; 90 → ×0,75)
    room = (1 - (q - 80).clip(lower=0) / 40).clip(lower=.4)
    growth = age_growth(_col(u, "idade")) * mult * room.fillna(1.0)
    pot = (q + growth).clip(upper=POT_CAP)
    # rodada 25: potencial para TODOS os jovens — sem nota atual (quase sem minutos), o potencial é ESTIMADO só pelos
    # sinais (seleção de base, minutos e nível, valor para a idade), partindo de um patamar de base e marcado como tal
    age = _col(u, "idade")
    no_q = q.isna() & age.notna() & (age <= 23)
    est = (48 + .22 * (talent - 50) + growth * .9).clip(35, 86)
    pot = pot.where(~no_q, est)
    out["potencial"] = pot.where(q.notna() | no_q).round(0)
    out["potencial_estimado_sem_nota"] = no_q
    out["potencial_crescimento"] = growth.where(q.notna() | no_q).round(1)
    out["potencial_talento"] = talent.round(0)
    m12 = _col(u, "minutos_12m").fillna(_col(u, "minutos")).fillna(0)
    out["potencial_confianca_pct"] = (100 * (.5 * (m12 / 1800).clip(0, 1) + .5 * evidence)).round(0)
    out["potencial_porque"] = [("ESTIMADO sem nota atual (poucos minutos): " if no_q.get(i) else "")
                               + _why(sig.loc[i], talent.loc[i], growth.loc[i], _col(u, "idade").get(i))
                               for i in u.index]
    return out


def _why(row: pd.Series, talent: float, growth: float, age: Any) -> str:
    vals = row.dropna()
    if pd.isna(age):
        return "idade desconhecida: sem projeção de crescimento (potencial = overall)"
    if float(age) >= 28:
        return "no auge ou depois dele: potencial = overall de hoje"
    if vals.empty:
        return f"poucos dados: crescimento típico da idade (+{growth:.0f})"
    top = vals.sort_values(ascending=False)
    up = [f"{SIGNAL_LABELS[k]} P{v:.0f}" for k, v in top.items() if v >= 60][:3]
    low = [f"{SIGNAL_LABELS[k]} P{v:.0f}" for k, v in top.items() if v < 40][-1:]
    txt = f"+{growth:.0f} até o auge (talento {talent:.0f}/100)"
    if up:
        txt += " · puxam para cima: " + ", ".join(up)
    if low:
        txt += " · limita: " + low[0]
    return txt
