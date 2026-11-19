"""
Rodada 13 — CARACTERÍSTICAS do jogador (maestro, motorzinho, artilheiro…).

Regra única: uma característica só aparece quando o atleta se destaca MUITO na comparação com quem joga na mesma
função (percentil por 90 minutos, com mínimo de minutos). Cada uma carrega o porquê com o número e o percentil.
Sem dado medido, a característica não é testada (nunca vira "não tem").
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

MIN_MINUTES = 600

# família → funções da base (mesmas siglas do Scout)
FAMILY = {"GK": "GK", "CB": "DEF", "RB": "FB", "LB": "FB", "FB": "FB", "DM": "MID", "CM": "MID", "MID": "MID",
          "AM": "ATT", "LW": "ATT", "RW": "ATT", "WIDE": "ATT", "ST": "ST", "CF": "ST"}

# (nome, emoji, famílias, [(métrica, percentil mínimo)], frase do porquê)
TRAITS: List[Dict[str, Any]] = [
    {"nome": "Artilheiro", "emoji": "🎯", "fam": {"ST", "ATT", "MID"}, "req": [("goals_p90", 90)],
     "why": "faz gols com frequência"},
    {"nome": "Oportunista", "emoji": "🦊", "fam": {"ST", "ATT"}, "req": [("conversao", 90), ("goals_p90", 70)],
     "why": "precisa de poucos chutes para marcar"},
    {"nome": "Finalizador", "emoji": "🥅", "fam": {"ST", "ATT", "MID"}, "req": [("shots_on_target_p90", 90)],
     "why": "acerta o gol com frequência"},
    {"nome": "Ameaça constante", "emoji": "💥", "fam": {"ST", "ATT", "MID"}, "req": [("xg_p90", 90)],
     "why": "chega sempre em boas posições de chute"},
    {"nome": "Maestro", "emoji": "🎼", "fam": {"MID", "ATT"}, "req": [("chances_created_p90", 85), ("pass_accuracy_pct", 70)],
     "why": "cria chances e passa com segurança"},
    {"nome": "Criativo", "emoji": "✨", "fam": {"MID", "ATT", "ST", "FB"}, "req": [("xa_p90", 90)],
     "why": "dá passes que viram chance clara"},
    {"nome": "Garçom", "emoji": "🍽️", "fam": {"MID", "ATT", "ST", "FB"}, "req": [("assists_p90", 90)],
     "why": "transforma passe em assistência"},
    {"nome": "Driblador", "emoji": "🌀", "fam": {"ATT", "ST", "MID", "FB"}, "req": [("dribbles_p90", 90)],
     "why": "vence o marcador no um contra um"},
    {"nome": "Velocista", "emoji": "⚡", "fam": {"ATT", "ST", "FB", "MID", "DEF"}, "req": [("sprints_p90", 90)],
     "why": "faz muitos piques em alta velocidade (só ligas que medem)"},
    {"nome": "Apoio ao ataque", "emoji": "🏃", "fam": {"FB"}, "req": [("chances_created_p90", 85)],
     "why": "lateral que chega à frente e cria"},
    {"nome": "Motorzinho", "emoji": "🔋", "fam": {"MID", "FB", "ATT"}, "req": [("recoveries_p90", 80), ("def_actions_p90", 80)],
     "why": "recupera bola e participa de tudo sem a bola"},
    {"nome": "Desarme", "emoji": "🦶", "fam": {"DEF", "FB", "MID"}, "req": [("tackles_p90", 90)],
     "why": "tira a bola no desarme"},
    {"nome": "Leitura de jogo", "emoji": "🧠", "fam": {"DEF", "FB", "MID"}, "req": [("interceptions_p90", 90)],
     "why": "corta passes antes de chegarem"},
    {"nome": "Defesa aérea", "emoji": "🗼", "fam": {"DEF", "MID", "FB"}, "req": [("aerials_won_p90", 90)],
     "why": "ganha as bolas pelo alto"},
    {"nome": "Pivô aéreo", "emoji": "🗼", "fam": {"ST", "ATT"}, "req": [("aerials_won_p90", 90)],
     "why": "referência pelo alto no ataque"},
    {"nome": "Xerife", "emoji": "🛡️", "fam": {"DEF"}, "req": [("clearances_p90", 90)],
     "why": "afasta o perigo da área"},
    {"nome": "Pitbull", "emoji": "🐕", "fam": {"MID", "DEF", "FB"}, "req": [("tackles_p90", 80), ("fouls_p90", 85)],
     "why": "marcação agressiva, faz falta para cortar o jogo"},
    {"nome": "Passe seguro", "emoji": "📐", "fam": {"DEF", "FB", "MID", "ATT"}, "req": [("pass_accuracy_pct", 93)],
     "why": "quase não erra passe"},
    {"nome": "Paredão", "emoji": "🧱", "fam": {"GK"}, "req": [("saves_p90", 85), ("gols_evitados_p90", 75)],
     "why": "defende mais do que o esperado pela qualidade dos chutes"},
    {"nome": "Defesas difíceis", "emoji": "🧤", "fam": {"GK"}, "req": [("gols_evitados_p90", 90)],
     "why": "evita gols que a média dos goleiros sofreria"},
    {"nome": "Regularidade", "emoji": "📈", "fam": {"GK", "DEF", "FB", "MID", "ATT", "ST"}, "req": [("rating_12m", 90)],
     "why": "nota alta jogo após jogo"},
]

COMPLETE = {"DEF": ("Zagueiro completo", ["def_actions_p90", "interceptions_p90", "clearances_p90", "aerials_won_p90",
                                          "pass_accuracy_pct"]),
            "MID": ("Meia completo", ["chances_created_p90", "xa_p90", "def_actions_p90", "interceptions_p90",
                                      "pass_accuracy_pct", "goals_p90"]),
            "ST": ("Atacante completo", ["goals_p90", "xg_p90", "xa_p90", "aerials_won_p90", "shots_on_target_p90"]),
            "FB": ("Lateral completo", ["def_actions_p90", "interceptions_p90", "chances_created_p90", "xa_p90"]),
            "ATT": ("Atacante de lado completo", ["goals_p90", "xa_p90", "chances_created_p90", "dribbles_p90"])}

LABELS = {"goals_p90": "gols por 90", "conversao": "gols por chute", "shots_on_target_p90": "chutes no gol por 90",
          "xg_p90": "xG por 90", "chances_created_p90": "chances criadas por 90", "pass_accuracy_pct": "% de passes certos",
          "xa_p90": "xA por 90", "assists_p90": "assistências por 90", "dribbles_p90": "dribles certos por 90",
          "sprints_p90": "piques por 90", "recoveries_p90": "recuperações por 90", "def_actions_p90": "ações defensivas por 90",
          "tackles_p90": "desarmes por 90", "interceptions_p90": "interceptações por 90",
          "aerials_won_p90": "duelos aéreos ganhos por 90", "clearances_p90": "cortes por 90", "fouls_p90": "faltas por 90",
          "saves_p90": "defesas por 90", "gols_evitados_p90": "gols evitados por 90", "rating_12m": "nota média (12 meses)"}


def _family(role: Any) -> str:
    return FAMILY.get(str(role or "").upper(), "")


def _derived(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    if "goals_p90" in d and "shots_p90" in d:
        shots = pd.to_numeric(d["shots_p90"], errors="coerce")
        d["conversao"] = (pd.to_numeric(d["goals_p90"], errors="coerce") / shots.where(shots > 0.4))
    if "xgot_faced_p90" in d and "goals_conceded_p90" in d:
        d["gols_evitados_p90"] = (pd.to_numeric(d["xgot_faced_p90"], errors="coerce")
                                  - pd.to_numeric(d["goals_conceded_p90"], errors="coerce"))
    if "rating_12m" not in d and "rating_media" in d:
        d["rating_12m"] = d["rating_media"]
    return d


def add_traits(universe: pd.DataFrame) -> pd.DataFrame:
    """Coluna `caracteristicas` (lista de dicts com nome, emoji, porquê, percentil) e `caracteristicas_top` (até 3)."""
    if universe is None or universe.empty:
        return universe
    d = _derived(universe)
    fam = d.get("papel", pd.Series(index=d.index, dtype=object)).map(_family)
    mins = pd.to_numeric(d.get("minutos_12m", pd.Series(index=d.index, dtype=float)), errors="coerce").fillna(0)
    ok = mins >= MIN_MINUTES
    metrics = sorted({m for t in TRAITS for m, _ in t["req"]} | {m for _, ms in COMPLETE.values() for m in ms})
    pct: Dict[str, pd.Series] = {}
    for m in metrics:
        if m not in d:
            continue
        v = pd.to_numeric(d[m], errors="coerce").where(ok)
        pct[m] = v.groupby(fam).rank(pct=True) * 100
    out: List[List[Dict[str, Any]]] = []
    for i in d.index:
        f = fam.get(i, "")
        found: List[Dict[str, Any]] = []
        if not f or not ok.get(i, False):
            out.append(found)
            continue
        for t in TRAITS:
            if f not in t["fam"]:
                continue
            vals = []
            for m, need in t["req"]:
                p = pct.get(m)
                pv = None if p is None else p.get(i)
                if pv is None or pd.isna(pv) or pv < need:
                    vals = None
                    break
                vals.append((m, float(pv)))
            if vals:
                m0, p0 = vals[0]
                raw = pd.to_numeric(d.at[i, m0], errors="coerce")
                found.append({"nome": t["nome"], "emoji": t["emoji"], "percentil": round(min(v for _, v in vals)),
                              "porque": f"{t['why']}: {LABELS.get(m0, m0)} {raw:.2f} — acima de {p0:.0f}% dos "
                                        f"jogadores da mesma função" if pd.notna(raw) else t["why"]})
        if f in COMPLETE:
            name, ms = COMPLETE[f]
            hits = [(m, float(pct[m].get(i))) for m in ms if m in pct and pd.notna(pct[m].get(i)) and pct[m].get(i) >= 70]
            if len(hits) >= max(3, len(ms) - 2):
                found.append({"nome": name, "emoji": "⭐", "percentil": round(min(v for _, v in hits)),
                              "porque": f"acima de 70% da função em {len(hits)} de {len(ms)} fundamentos: "
                                        + ", ".join(LABELS.get(m, m) for m, _ in hits)})
        prec = pd.to_numeric(d.at[i, "precocidade"], errors="coerce") if "precocidade" in d else np.nan
        age = pd.to_numeric(d.at[i, "idade"], errors="coerce") if "idade" in d else np.nan
        if pd.notna(prec) and pd.notna(age) and age <= 21 and prec >= 85:
            found.append({"nome": "Grande promessa", "emoji": "🌱", "percentil": round(prec),
                          "porque": f"valor de mercado e minutos de profissional acima de {prec:.0f}% de quem tem a "
                                    f"mesma idade ({age:.0f} anos)"})
        found.sort(key=lambda x: -x["percentil"])
        out.append(found)
    # jovens com pouca minutagem também podem ser promessa (não exigem os 600 min das outras características)
    res = universe.copy()
    res["caracteristicas"] = out
    if "precocidade" in d and "idade" in d:
        prec = pd.to_numeric(d["precocidade"], errors="coerce")
        age = pd.to_numeric(d["idade"], errors="coerce")
        for i in d.index[(~ok) & age.le(21) & prec.ge(85)]:
            res.at[i, "caracteristicas"] = [{"nome": "Grande promessa", "emoji": "🌱", "percentil": round(prec[i]),
                                             "porque": f"valor de mercado e minutos acima de {prec[i]:.0f}% de quem tem "
                                                       f"a mesma idade ({age[i]:.0f} anos)"}]
    # rodada 20: seleção de BASE (Mundial/Sul-Americano Sub-20, Mundial Sub-17, Euros de base) — sinal de promessa
    if "selecao_base_jogos" in res:
        caps = pd.to_numeric(res["selecao_base_jogos"], errors="coerce")
        comps = res.get("selecao_base_comp", pd.Series("", index=res.index)).fillna("").astype(str)
        for i in res.index[caps.fillna(0) >= 1]:
            n = int(caps[i])
            item = {"nome": "Seleção de base", "emoji": "🏅", "percentil": min(99, 88 + n),
                    "porque": f"{n} jogo{'s' if n > 1 else ''} por seleção de base ({comps[i] or 'competições de base'})"}
            cur = [x for x in (res.at[i, "caracteristicas"] or []) if x.get("nome") != "Seleção de base"]
            age_i = pd.to_numeric(res.at[i, "idade"], errors="coerce") if "idade" in res else np.nan
            if n >= 3 and (pd.isna(age_i) or age_i <= 21) and not any(x.get("nome") == "Grande promessa" for x in cur):
                cur.append({"nome": "Grande promessa", "emoji": "🌱", "percentil": min(99, 85 + n),
                            "porque": f"titular frequente da seleção de base ({n} jogos)"})
            res.at[i, "caracteristicas"] = sorted(cur + [item], key=lambda x: -x["percentil"])
    res["caracteristicas_top"] = res["caracteristicas"].map(
        lambda xs: " · ".join(f"{x['emoji']} {x['nome']}" for x in (xs or [])[:3]))
    return res


def traits_html(items: List[Dict[str, Any]], limit: int | None = 3, why: bool = False) -> str:
    items = list(items or [])[: limit or None]
    if not items:
        return '<span style="color:#98A6BF;font-size:.85rem">sem destaque fora da curva na função</span>'
    chips = []
    for x in items:
        tip = f' title="{x["porque"]}"'
        body = f'{x["emoji"]} {x["nome"]}' + (f'<div style="font-size:.78rem;color:#98A6BF;margin-top:2px">{x["porque"]}</div>'
                                              if why else "")
        chips.append(f'<span{tip} style="display:inline-block;background:#0F1A2E;border:1px solid #1E2A44;'
                     f'border-radius:10px;padding:3px 9px;margin:2px 4px 2px 0;font-size:.85rem">{body}</span>')
    return "".join(chips)
