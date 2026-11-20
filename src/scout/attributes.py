"""
Rodada 23/24 — ATRIBUTOS no estilo Football Manager (rodada 24: escala 1–100), mas MEDIDOS: cada atributo vem de números reais da FotMob/ESPN
(por 90 minutos e % de acerto) comparados com os jogadores da MESMA posição no universo do Scout.

* 1–100 = percentil na função (P5 ≈ 6 · P50 ≈ 50 · P95 ≈ 95), puxado para 50 quando há poucos minutos
  (minutos / (minutos + 900)) — quem jogou pouco não ganha 19 por sorte.
* Só aparece o que é OBSERVÁVEL. Velocidade/explosão só onde a liga mede sprints; atributos mentais que nenhuma fonte
  mede (liderança, determinação, decisões) ficam como "não observável" — nunca chutados.
* Grupos para o radar "Análise de atributos" (Ataque, Técnica, Visão, Defesa, Jogo aéreo, Passe, Físico, Trabalho).
* Estrelas de CAPACIDADE e POTENCIAL relativas ao nível da liga do atleta (ou do clube que está contratando): o titular
  típico da liga = 2,5–3 estrelas, como o "Bom para o Brasileirão" do FM.
* Nota da contratação (1–100) e prós/contras com o porquê de cada item.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# atributo → [(coluna, peso)]; peso negativo = quanto MENOS, melhor
ATTRS: Dict[str, List[Tuple[str, float]]] = {
    "Finalização": [("goals_p90", 1.0), ("xg_p90", .6), ("shot_acc_pct", .7)],
    "Cabeceamento": [("aerial_pct", 1.0), ("aerials_won_p90", .7)],
    "Cruzamentos": [("cross_pct", .8), ("crosses_acc_p90", 1.0)],
    "Passe": [("pass_accuracy_pct", 1.0), ("line_breaking_p90", .6)],
    "Lançamentos": [("long_ball_pct", 1.0), ("long_balls_p90", .6)],
    "Drible": [("dribbles_p90", 1.0), ("dribble_pct", .7)],
    "Técnica": [("touches_p90", .6), ("dispossessed_p90", -.8), ("dribble_pct", .4)],
    "Desarme": [("tackles_p90", 1.0), ("duels_won_pct", .8)],
    "Antecipação": [("interceptions_p90", 1.0), ("recoveries_p90", .7)],
    "Visão de jogo": [("chances_created_p90", 1.0), ("xa_p90", .9), ("final_third_passes_p90", .6)],
    "Segurança com a bola": [("dispossessed_p90", -1.0), ("errors_p90", -.6)],
    "Trabalho defensivo": [("def_actions_p90", 1.0), ("recoveries_p90", .6)],
    "Explosão (sprints)": [("sprints_p90", 1.0)],
    "Defesas (goleiro)": [("saves_p90", 1.0)],
}
GK_ATTRS = ["Defesas (goleiro)", "Cabeceamento", "Passe", "Lançamentos", "Segurança com a bola"]
NOT_OBSERVABLE = ["Liderança", "Determinação", "Decisões", "Posicionamento sem bola", "Velocidade (onde a liga não mede)"]
GROUPS = {"Ataque": ["Finalização"], "Técnica": ["Drible", "Técnica"], "Visão": ["Visão de jogo"],
          "Passe": ["Passe", "Lançamentos", "Cruzamentos"], "Defesa": ["Desarme", "Antecipação"],
          "Jogo aéreo": ["Cabeceamento"], "Físico": ["Explosão (sprints)"], "Trabalho": ["Trabalho defensivo", "Segurança com a bola"]}
ICON = {"Finalização": "🎯", "Cabeceamento": "🗼", "Cruzamentos": "↪️", "Passe": "🔗", "Lançamentos": "📐", "Drible": "🌀",
        "Técnica": "🪄", "Desarme": "🛡️", "Antecipação": "👁️", "Visão de jogo": "💡", "Segurança com a bola": "🔒",
        "Trabalho defensivo": "🔋", "Explosão (sprints)": "⚡", "Defesas (goleiro)": "🧤"}
MIN_SHRINK = 900.0


def _col(u: pd.DataFrame, c: str) -> pd.Series:
    return pd.to_numeric(u[c], errors="coerce") if c in u else pd.Series(np.nan, index=u.index, dtype=float)


def family(u: pd.DataFrame) -> pd.Series:
    from src.scout.overall import FAMILY

    if "_fam" in u and u["_fam"].astype(str).str.len().gt(0).any():
        return u["_fam"].fillna("").astype(str)
    return (u["papel"] if "papel" in u else pd.Series("", index=u.index)).map(FAMILY).fillna("")


def compute(u: pd.DataFrame) -> pd.DataFrame:
    """Atributos 1–100 de todos (colunas `atr_<nome>`), comparando dentro da posição; NaN = não medido."""
    out = pd.DataFrame(index=u.index)
    if u is None or u.empty:
        return out
    fam = family(u)
    mins = _col(u, "minutos_12m").fillna(_col(u, "minutos")).fillna(0)
    elig = mins >= 300
    shrink = mins / (mins + MIN_SHRINK)
    for name, parts in ATTRS.items():
        num = pd.Series(0.0, index=u.index)
        den = pd.Series(0.0, index=u.index)
        for col, w in parts:
            v = _col(u, col).where(elig)
            if v.notna().sum() < 8:
                continue
            p = v.groupby(fam).rank(pct=True)
            if w < 0:
                p = 1 - p
            ok = p.notna()
            num[ok] += abs(w) * p[ok]
            den[ok] += abs(w)
        pct = (num / den.replace(0, np.nan))
        # rodada 24: escala 1–100 (pedido do usuário: "só uma de 1 a 100"); poucos minutos → perto de 50
        score = 1 + 99 * pct
        score = 50 + (score - 50) * shrink
        out[f"atr_{name}"] = score.round(0).clip(1, 100).where(pct.notna())
    gk = fam == "GK"
    for name in ATTRS:
        c = f"atr_{name}"
        if name not in GK_ATTRS:
            out.loc[gk, c] = np.nan                                # goleiro não é medido como atacante
        elif name == "Defesas (goleiro)":
            out.loc[~gk, c] = np.nan
    return out


def groups(row: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Média dos atributos de cada grupo (1–100) — base do radar; grupo sem medida = None."""
    res = {}
    for g, names in GROUPS.items():
        vals = [row.get(f"atr_{n}") for n in names]
        vals = [float(v) for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
        res[g] = round(float(np.mean(vals)), 1) if vals else None
    return res


# ------------------------------------------------------------------ estrelas e nível da liga
def league_reference(u: pd.DataFrame, min_minutes: int = 900) -> Dict[str, float]:
    """Overall do 'titular típico' de cada liga = P75 do overall de quem jogou ≥ 900 min nela."""
    liga = u.get("clube_liga", u.get("ultima_competicao", pd.Series("", index=u.index))).fillna("").astype(str)
    q = _col(u, "qualidade")
    m = _col(u, "minutos_12m").fillna(_col(u, "minutos")).fillna(0)
    d = pd.DataFrame({"liga": liga, "q": q})[(m >= min_minutes) & q.notna() & (liga != "")]
    g = d.groupby("liga")["q"]
    ref = g.quantile(.75)
    return {k: float(v) for k, v in ref[g.size() >= 15].items()}


def stars(ovr: Any, ref: Optional[float]) -> Optional[float]:
    """Overall → estrelas (0,5–5) contra o titular típico da liga (ref = 3 estrelas)."""
    try:
        o = float(ovr)
    except (TypeError, ValueError):
        return None
    if np.isnan(o):
        return None
    base = ref if ref else 70.0
    s = 3.0 + (o - base) / 5.0
    return float(np.clip(round(s * 2) / 2, .5, 5))


def level_label(ovr: Any, ref: Optional[float], liga: str) -> str:
    try:
        o = float(ovr)
    except (TypeError, ValueError):
        return "sem nota"
    if not ref:
        return "nível da liga desconhecido"
    if o >= 86:
        return "nível de elite mundial"
    d = o - ref
    return (f"destaque para a {liga}" if d >= 6 else f"bom para a {liga}" if d >= 0 else
            f"razoável para a {liga}" if d >= -5 else f"abaixo do nível da {liga}")


def star_html(s: Optional[float], color: str = "#22D3EE") -> str:
    if s is None:
        return '<span style="color:#64748B">—</span>'
    full, half = int(s), (s - int(s)) >= .5
    out = "".join(f'<span style="color:{color}">★</span>' for _ in range(full))
    if half:
        out += f'<span style="background:linear-gradient(90deg,{color} 50%,#334155 50%);-webkit-background-clip:text;color:transparent">★</span>'
    out += "".join('<span style="color:#334155">★</span>' for _ in range(5 - full - (1 if half else 0)))
    return out


# ------------------------------------------------------------------ veredito e prós/contras
def verdict(score_scout: Any) -> Tuple[Optional[int], str]:
    """score do Scout (0–100) → nota da contratação 1–100 + frase (rodada 24: sem a escala 1–20)."""
    try:
        v = int(np.clip(round(float(score_scout)), 1, 100))
    except (TypeError, ValueError):
        return None, "sem avaliação"
    txt = ("Seria uma excelente contratação" if v >= 85 else "Seria uma boa contratação" if v >= 70 else
           "Contratação razoável" if v >= 55 else "Contratação duvidosa" if v >= 40 else "Não recomendado")
    return v, txt


def pros_cons(row: Dict[str, Any], fam_label: str = "da posição") -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Prós e contras (ícone, texto) a partir dos atributos medidos, do pé, da altura, da fase e do realismo."""
    pros, cons = [], []
    for name in ATTRS:
        v = row.get(f"atr_{name}")
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        if v >= 75:
            pros.append((ICON.get(name, "✅"), f"{name}: {int(v)}/100 — entre os melhores {fam_label}"))
        elif v <= 28:
            cons.append((ICON.get(name, "⚠️"), f"{name}: {int(v)}/100 — bem abaixo {fam_label}"))
    tr = row.get("caracteristicas_top") or row.get("caracteristicas")
    if isinstance(tr, str) and tr:
        for t in [x.strip() for x in tr.replace(";", ",").split(",") if x.strip()][:3]:
            pros.append(("⭐", f"Característica: {t}"))
    elif isinstance(tr, (list, tuple)):
        for t in list(tr)[:3]:
            label = t.get("nome") if isinstance(t, dict) else str(t)
            if label:
                pros.append(("⭐", f"Característica: {label}"))
    pe = str(row.get("pe") or "").lower()
    if pe in ("both", "ambos", "ambidestro"):
        pros.append(("🦶", "Usa bem os dois pés"))
    elif pe in ("left", "right", "esquerdo", "direito"):
        cons.append(("🦶", f"Usa basicamente o pé {'esquerdo' if pe in ('left', 'esquerdo') else 'direito'}"))
    h = row.get("altura_cm")
    try:
        h = float(h)
    except (TypeError, ValueError):
        h = None
    fam = str(row.get("_fam") or "")
    if h and fam in ("CB", "GK", "ST"):
        if h >= 190:
            pros.append(("📏", f"Muito alto para a posição ({h:.0f} cm)"))
        elif h <= 178:
            cons.append(("📏", f"Baixo para a posição ({h:.0f} cm)"))
    form = row.get("forma_5")
    if isinstance(form, (list, tuple)) and len(form) >= 3:
        f = float(np.mean(form))
        base = row.get("rating_12m")
        try:
            base = float(base)
        except (TypeError, ValueError):
            base = None
        if base and f - base >= .3:
            pros.append(("📈", f"Em boa fase: nota {f:.2f} nos últimos jogos (média do ano {base:.2f})"))
        elif base and base - f >= .3:
            cons.append(("📉", f"Fase ruim: nota {f:.2f} nos últimos jogos (média do ano {base:.2f})"))
    yj = row.get("selecao_base_jogos")
    try:
        if yj and float(yj) > 0:
            pros.append(("🏅", f"Seleção de base: {int(float(yj))} jogo(s) ({row.get('selecao_base_comp') or ''})"))
    except (TypeError, ValueError):
        pass
    real = row.get("realismo")
    if isinstance(real, dict):
        if real.get("penalidade_estrangeiros"):
            cons.append(("🌍", "Conta no limite de estrangeiros do campeonato"))
        if real.get("patamar"):
            cons.append(("💰", str(real["patamar"])))
        if real.get("oportunidade_emprestimo"):
            pros.append(("🤝", "Oportunidade de empréstimo (joga pouco ou contrato perto do fim)"))
    return pros[:8], cons[:8]
