"""Rodada 23 — "Visão geral (olheiro)" do jogador, inspirada no Football Manager, com números MEDIDOS:
cabeçalho (posição, clube, idade, nacionalidade, altura, pé, valor, contrato), capacidade e potencial em estrelas pelo nível
da liga, atributos 1–20, radar "Análise de atributos", forma dos últimos jogos, prós/contras e (no Scout) o veredito do
olheiro com a comparação do elenco na posição."""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st

from src.ui import fm


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return None if np.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _money(v: Any) -> str:
    v = _num(v)
    if not v:
        return "—"
    return f"€ {v / 1e6:.1f} mi" if v >= 1e6 else f"€ {v / 1e3:.0f} mil"


def _date(v: Any) -> str:
    d = pd.to_datetime(v, errors="coerce")
    return "n/d" if pd.isna(d) else d.strftime("%d/%m/%Y")


def header(row: Dict[str, Any]) -> None:
    from src.scout import attributes as AT
    from src.scout import snapshot as S

    u = S.cached_universe()
    refs = AT.league_reference(u) if u is not None else {}
    liga = str(row.get("clube_liga") or row.get("ultima_competicao") or "")
    ref = refs.get(liga)
    if ref is None and u is not None and "qualidade" in u:      # liga com poucos jogadores na base: régua do universo
        q = pd.to_numeric(u["qualidade"], errors="coerce").dropna()
        ref = float(q.quantile(.75)) if len(q) >= 30 else None
        liga = liga or "base"
    ovr, pot = row.get("qualidade"), row.get("potencial", row.get("potencial_teto"))
    age = _num(row.get("idade"))
    try:
        from src.scout.engine import ROLE_LABELS
    except Exception:
        ROLE_LABELS = {}
    role = str(row.get("papel_alvo_label") or ROLE_LABELS.get(str(row.get("papel") or ""), row.get("papel") or ""))
    bits = [role, str(row.get("clube") or ""),
            f"{int(age)} anos" if age else "idade n/d", str(row.get("nacionalidade") or "nacionalidade n/d")]
    h = _num(row.get("altura_cm"))
    if h:
        bits.append(f"{h:.0f} cm")
    pe = str(row.get("pe") or "")
    if pe:
        bits.append({"right": "pé direito", "left": "pé esquerdo", "both": "ambidestro"}.get(pe.lower(), pe))
    c1, c2, c3 = st.columns([2.2, 1.4, 1.4])
    with c1:
        fm.panel("Informação-chave", fm.CYAN)
        st.markdown(f'<div class="fm-stars"><div class="lb">{" · ".join(b for b in bits if b)}</div>'
                    f'<div class="tx">Valor {_money(row.get("valor_mercado_eur"))} · contrato até '
                    f'{_date(row.get("fim_contrato"))} · minutos no ano {int(_num(row.get("minutos_12m")) or 0)}'
                    f' · nota média {row.get("rating_12m") if _num(row.get("rating_12m")) else "—"}</div></div>',
                    unsafe_allow_html=True)
    with c2:
        fm.stars_line("Capacidade atual", AT.stars(ovr, ref), AT.level_label(ovr, ref, liga or "liga"),
                      int(ovr) if _num(ovr) is not None else None)
    with c3:
        fm.stars_line("Capacidade potencial", AT.stars(pot, ref),
                      str(row.get("potencial_porque") or "")[:90], int(pot) if _num(pot) is not None else None)


def overview(row: Dict[str, Any], key: str, form: Optional[pd.DataFrame] = None) -> None:
    """A visão geral completa (cabeçalho + atributos + radar + forma + prós/contras)."""
    from src.scout import attributes as AT

    header(row)
    fam = str(row.get("_fam") or "")
    a, b = st.columns([1.6, 1])
    with a:
        fm.panel("Atributos (medidos)", fm.BLUE)
        fm.attr_table(row, gk=fam == "GK")
    with b:
        fm.radar(AT.groups(row), key=f"{key}_radar")
    c, d = st.columns(2)
    pros, cons = AT.pros_cons(row, "da posição")
    with c:
        fm.icon_list(pros, "pro", "Prós")
    with d:
        fm.icon_list(cons, "con", "Contras")
    if form is not None and not form.empty:
        _form_chart(form, key)


def _form_chart(f: pd.DataFrame, key: str) -> None:
    import plotly.graph_objects as go

    col = "nota" if "nota" in f and f["nota"].notna().any() else ("rating" if "rating" in f else None)
    if not col:
        return
    d = f.dropna(subset=[col]).head(10).iloc[::-1]
    if len(d) < 2:
        return
    fig = go.Figure(go.Scatter(x=list(range(1, len(d) + 1)), y=pd.to_numeric(d[col], errors="coerce"), mode="lines+markers",
                               line=dict(color=fm.CYAN, width=3), marker=dict(size=8, color="#E2E8F0"),
                               text=[f"{j} ({dt})" for j, dt in zip(d.get("jogo", [""] * len(d)), d.get("data", [""] * len(d)))],
                               hoverinfo="text+y"))
    fig.update_layout(title=dict(text="Forma (últimos jogos)", font=dict(size=13, color="#CBD5E1")), height=220,
                      margin=dict(l=30, r=10, t=36, b=20), paper_bgcolor="#090D16", plot_bgcolor="#0F1626",
                      xaxis=dict(visible=False), yaxis=dict(gridcolor="#1E2A44", color="#94A3B8"))
    st.plotly_chart(fig, use_container_width=True, key=f"{key}_form")


def squad_compare(row: Dict[str, Any], roster: pd.DataFrame, key: str) -> None:
    """FM 'Comparação da equipa': quem o clube já tem na posição, com capacidade e potencial em estrelas."""
    from src.scout import attributes as AT

    if roster is None or roster.empty or "papel" not in roster:
        return
    role = row.get("papel_alvo") or row.get("papel")
    same = roster[roster["papel"] == role].copy()
    cand = pd.DataFrame([{"nome": row.get("nome"), "qualidade": row.get("qualidade"),
                          "potencial": row.get("potencial", row.get("potencial_teto")), "cand": True}])
    same = same.assign(cand=False, potencial=same.get("potencial", same.get("potencial_teto")))
    t = pd.concat([same[["nome", "qualidade", "potencial", "cand"]], cand], ignore_index=True)
    t["q"] = pd.to_numeric(t["qualidade"], errors="coerce")
    t = t.sort_values("q", ascending=False).head(6)
    ref = _num(pd.to_numeric(roster.get("qualidade"), errors="coerce").quantile(.75)) if "qualidade" in roster else None
    rows = "".join(
        f'<tr style="{"background:#0E3B2E" if r.cand else ""}"><td>{i}</td><td>{fm._e(r.nome)}</td>'
        f'<td>{AT.star_html(AT.stars(r.qualidade, ref))}</td><td>{AT.star_html(AT.stars(r.potencial, ref), "#3B82F6")}</td></tr>'
        for i, r in enumerate(t.itertuples(), 1))
    fm.panel(f"Comparação do elenco · {row.get('papel_alvo_label') or role}", fm.CYAN, "estrelas contra o titular típico do elenco")
    st.markdown(f'<table class="fm-facts"><thead><tr><th>#</th><th>Jogador</th><th>Capacidade</th><th>Potencial</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>', unsafe_allow_html=True)
