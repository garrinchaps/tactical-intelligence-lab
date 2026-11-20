"""
Rodada 23 — componentes visuais no espírito do Football Manager, com as CORES do laboratório (fundo #090D16, painéis com
borda #1E2A44, azul #22D3EE/#3B82F6 para o nosso lado, vermelho #EF4444 para o rival, verde/vermelho para prós/contras).

panel(título)            → cabeçalho de painel
icon_list(itens, tipo)   → linhas com ícone (prós, contras, notícias, pontos fortes/fracos)
attr_table(linha)        → atributos 1–20 coloridos em colunas (técnicos / mentais medidos / físicos)
radar(grupos)            → "Análise de atributos" (plotly polar, sem barra de ferramentas)
stars_line(...)          → capacidade/potencial em estrelas com a frase de nível
verdict_card(nota, frase)→ cartão verde/amarelo/vermelho do olheiro (1–20)
people_tiles(...)        → capitão / jogador-chave / melhor marcador… com iniciais
facts_table(linhas)      → "Factos": nosso × liga, com a diferença colorida
rank_list(...)           → estatísticas de equipe com a colocação ("26 — Melhor", "10 — 7º melhor")
"""

from __future__ import annotations

import html
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import streamlit as st

GREEN, RED, AMBER, BLUE, CYAN = "#22C55E", "#EF4444", "#F59E0B", "#3B82F6", "#22D3EE"


def _e(x: Any) -> str:
    return html.escape(str(x if x is not None else ""))


def panel(title: str, color: str = "#1E2A44", sub: str = "") -> None:
    st.markdown(f'<div class="fm-panel-h" style="border-color:{color}"><span>{_e(title)}</span>'
                + (f'<small>{_e(sub)}</small>' if sub else "") + '</div>', unsafe_allow_html=True)


def icon_list(items: Sequence[Tuple[str, str]], kind: str = "neutral", title: str = "", sub_items: Optional[Sequence[str]] = None) -> None:
    color = {"pro": GREEN, "con": RED, "warn": AMBER, "neutral": "#334155", "blue": CYAN}.get(kind, "#334155")
    head = (f'<div class="fm-list-h" style="background:{color}">{_e(title)}</div>' if title else "")
    rows = "".join(
        f'<div class="fm-row"><div class="fm-ic" style="background:{color}22;border-color:{color}66">{_e(ic)}</div>'
        f'<div class="fm-tx">{_e(tx)}' + (f'<div class="fm-sub">{_e(sub_items[i])}</div>' if sub_items and i < len(sub_items) and sub_items[i] else "")
        + '</div></div>' for i, (ic, tx) in enumerate(items))
    if not items:
        rows = '<div class="fm-row"><div class="fm-tx" style="color:#64748B">nada fora da curva nos números medidos</div></div>'
    st.markdown(f'<div class="fm-list">{head}{rows}</div>', unsafe_allow_html=True)


def attr_color(v: Any) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "#475569"
    if v != v:                                          # NaN = não medido
        return "#475569"
    return GREEN if v >= 16 else CYAN if v >= 12 else "#CBD5E1" if v >= 8 else AMBER if v >= 5 else RED


def attr_table(row: Dict[str, Any], gk: bool = False) -> None:
    from src.scout import attributes as AT

    tech = ["Finalização", "Cabeceamento", "Cruzamentos", "Passe", "Lançamentos", "Drible", "Técnica", "Desarme"]
    ment = ["Antecipação", "Visão de jogo", "Segurança com a bola", "Trabalho defensivo"]
    phys = ["Explosão (sprints)"]
    if gk:
        tech, ment = ["Defesas (goleiro)", "Cabeceamento", "Passe", "Lançamentos"], ["Segurança com a bola"]

    def col(title, names, extra=()):
        rows = []
        for n in names:
            v = row.get(f"atr_{n}")
            ok = v is not None and v == v
            rows.append(f'<div class="fm-attr"><span>{_e(n)}</span><b style="color:{attr_color(v)}">'
                        f'{int(v) if ok else "—"}</b></div>')
        rows += [f'<div class="fm-attr na"><span>{_e(n)}</span><b>não obs.</b></div>' for n in extra]
        return f'<div class="fm-attr-col"><div class="fm-attr-h">{_e(title)}</div>{"".join(rows)}</div>'
    st.markdown('<div class="fm-attrs">' + col("TÉCNICOS", tech) + col("MENTAIS (medidos)", ment, AT.NOT_OBSERVABLE[:3])
                + col("FÍSICOS", phys, ["Velocidade", "Resistência"]) + '</div>', unsafe_allow_html=True)
    st.caption("1–20 = posição contra os jogadores da MESMA função no universo do Scout (números por 90 e % de acerto da "
               "FotMob/ESPN), puxada para 10 com poucos minutos. 'não obs.' = nenhuma fonte aberta mede (não é chute).")


def radar(groups: Dict[str, Optional[float]], key: str, title: str = "Análise de atributos", compare: Optional[Dict[str, Optional[float]]] = None):
    import plotly.graph_objects as go

    labs = [k for k, v in groups.items() if v is not None]
    if len(labs) < 3:
        st.caption("Atributos medidos insuficientes para o radar.")
        return
    fig = go.Figure()
    vals = [groups[k] for k in labs]
    fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=labs + labs[:1], fill="toself", name="atleta",
                                  line=dict(color=CYAN), fillcolor="rgba(34,211,238,.25)"))
    if compare:
        cv = [compare.get(k) or 0 for k in labs]
        fig.add_trace(go.Scatterpolar(r=cv + cv[:1], theta=labs + labs[:1], fill="toself", name="comparação",
                                      line=dict(color=RED), fillcolor="rgba(239,68,68,.15)"))
    fig.update_layout(title=dict(text=title, font=dict(size=13, color="#CBD5E1")), height=320, showlegend=bool(compare),
                      margin=dict(l=30, r=30, t=40, b=20), paper_bgcolor="#090D16",
                      polar=dict(bgcolor="#0F1626", radialaxis=dict(range=[0, 20], showticklabels=False, gridcolor="#1E2A44"),
                                 angularaxis=dict(gridcolor="#1E2A44", tickfont=dict(color="#CBD5E1", size=11))))
    st.plotly_chart(fig, use_container_width=True, key=key)


def stars_line(label: str, s: Optional[float], text: str, value: Any = None) -> None:
    from src.scout.attributes import star_html

    st.markdown(f'<div class="fm-stars"><div class="lb">{_e(label)}</div><div class="st">{star_html(s)}'
                + (f' <b>{_e(value)}</b>' if value is not None and value == value else "")
                + f'</div><div class="tx">{_e(text)}</div></div>', unsafe_allow_html=True)


def verdict_card(score: Optional[int], text: str) -> None:
    if score is None:
        return
    color = GREEN if score >= 14 else AMBER if score >= 10 else RED
    st.markdown(f'<div class="fm-verdict" style="background:{color}22;border-color:{color}">'
                f'<div class="n" style="border-color:{color};color:{color}">{score}</div><div class="t">{_e(text)}.</div></div>',
                unsafe_allow_html=True)


def people_tiles(items: Sequence[Tuple[str, str, str]], cols: int = 4) -> None:
    """[(papel, nome, detalhe)] → quadradinhos com iniciais (sem fotos: as fontes abertas não trazem imagem licenciada)."""
    if not items:
        return
    columns = st.columns(min(cols, len(items)))
    for i, (role, name, det) in enumerate(items):
        ini = "".join(w[0] for w in str(name).split()[:2]).upper() or "?"
        columns[i % len(columns)].markdown(
            f'<div class="fm-person"><div class="r">{_e(role)}</div><div class="av">{_e(ini)}</div>'
            f'<div class="n">{_e(name)}</div><div class="d">{_e(det)}</div></div>', unsafe_allow_html=True)


def facts_table(rows: Sequence[Dict[str, Any]], a: str, b: str) -> None:
    """rows: {"fato", "a", "b", "melhor": "a"|"b"|None, "dif"} — FM 'Comparação de equipa' / 'Factos'."""
    body = "".join(
        f'<tr><td class="f">{_e(r["fato"])}</td><td style="color:{CYAN if r.get("melhor") == "a" else "#E2E8F0"}">{_e(r["a"])}</td>'
        f'<td style="color:{RED if r.get("melhor") == "b" else "#E2E8F0"}">{_e(r["b"])}</td>'
        f'<td style="color:{GREEN if r.get("melhor") == "a" else RED if r.get("melhor") == "b" else "#94A3B8"}">{_e(r.get("dif", ""))}</td></tr>'
        for r in rows)
    st.markdown(f'<table class="fm-facts"><thead><tr><th></th><th>{_e(a)}</th><th>{_e(b)}</th><th>Comparação</th></tr></thead>'
                f'<tbody>{body}</tbody></table>', unsafe_allow_html=True)


def rank_list(items: Sequence[Tuple[str, str, str]]) -> None:
    """[(ícone, título, 'valor — colocação')]."""
    rows = "".join(f'<div class="fm-row"><div class="fm-ic">{_e(ic)}</div><div class="fm-tx"><b>{_e(t)}</b>'
                   f'<div class="fm-sub">{_e(v)}</div></div></div>' for ic, t, v in items)
    st.markdown(f'<div class="fm-list">{rows}</div>', unsafe_allow_html=True)


def ordinal_rank(value: float, values: Iterable[float], higher_better: bool = True) -> str:
    vals = sorted([v for v in values if v == v], reverse=higher_better)
    if not vals or value != value:
        return "—"
    pos = 1 + sum(1 for v in vals if (v > value if higher_better else v < value))
    if pos == 1:
        return "Melhor"
    if pos == len(vals):
        return "Pior"
    return f"{pos}º melhor"
