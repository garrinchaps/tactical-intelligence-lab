"""Rodada 22 — tela da IDENTIDADE TÁTICA (página do time, pré-jogo do rival): cartões em linguagem de futebol, campinho
com as posições médias por fase (só jogos com lances), corredores, consistência, treinadores e contratação por função."""

from __future__ import annotations

import html
from typing import Any, Dict, Sequence

import pandas as pd
import streamlit as st

from src.ui.perf import timed as _perf_timed


@_perf_timed("identity._data")
@st.cache_data(show_spinner=False, max_entries=48, persist="disk")
def _data(names: tuple, version: str, n: int) -> Dict[str, Any]:
    from src.analytics import tactical_identity as TI
    from src.ui.context import get_service

    ident = TI.identity(get_service().db, list(names), n)
    ident["contratacao"] = TI.recruitment_needs(ident)
    # match_ids dos períodos (listas grandes) não precisam ir para a tela
    for c in ident.get("treinadores") or []:
        c.pop("match_ids", None)
    return ident


def _card(title: str, value: str, sub: str = "", color: str = "#22D3EE") -> str:
    return (f'<div style="background:#0F1626;border:1px solid #1E2A44;border-left:4px solid {color};border-radius:12px;'
            f'padding:.6rem .8rem;margin-bottom:.5rem"><div style="color:#94A3B8;font-size:.78rem">{html.escape(title)}</div>'
            f'<div style="font-size:1.25rem;font-weight:800;color:#E2E8F0">{html.escape(value)}</div>'
            f'<div style="color:#94A3B8;font-size:.78rem">{html.escape(sub)}</div></div>')


def _pitch(pos: Dict[str, Any], title: str):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=120, y1=80, line=dict(color="#2B3A55"), fillcolor="#0E3B2E")
    fig.add_shape(type="line", x0=60, y0=0, x1=60, y1=80, line=dict(color="#2B3A55"))
    for x0, x1 in ((0, 18), (102, 120)):
        fig.add_shape(type="rect", x0=x0, y0=18, x1=x1, y1=62, line=dict(color="#2B3A55"))
    if pos:
        names = list(pos)
        xs = [pos[n][0] for n in names]
        ys = [80 - pos[n][1] for n in names]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+text", text=[n.split()[-1] for n in names],
                                 textposition="top center", marker=dict(size=14, color="#22D3EE", line=dict(color="#090D16", width=2)),
                                 textfont=dict(color="#E2E8F0", size=10), hovertext=names, hoverinfo="text"))
    fig.update_layout(title=dict(text=title, font=dict(size=13, color="#CBD5E1")), height=300, margin=dict(l=4, r=4, t=30, b=4),
                      paper_bgcolor="#090D16", plot_bgcolor="#090D16", showlegend=False,
                      xaxis=dict(visible=False, range=[-2, 122]), yaxis=dict(visible=False, range=[-2, 82], scaleanchor="x"))
    return fig


def render(team: str, names: Sequence[str], version: str, key: str = "club") -> None:
    st.markdown("#### 🧭 Identidade tática")
    st.caption("Como o time se organiza com e sem a bola. Cada leitura diz a FONTE: lances (coordenadas) ou estatísticas "
               "por jogo (aproximação). Sem dados de rastreamento (tracking), não afirmamos linha de impedimento contínua "
               "nem compactação — só onde as ações aconteceram.")
    n = st.select_slider("Jogos analisados", [5, 10, 20, 40], value=20, key=f"ti_n_{key}")
    with st.spinner("Lendo o modelo de jogo…"):
        d = _data(tuple(names), version, int(n))
    for line in d.get("resumo") or []:
        st.markdown(f"- {line}")
    stv, evi = d.get("estatisticas") or {}, d.get("lances") or {}
    p, ref = stv.get("perfil") or {}, stv.get("referencia") or {}

    def fmt(v, suf=""):
        return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{v:.1f}{suf}"
    st.markdown("##### ⚽ Com a bola")
    c = st.columns(4)
    m = evi.get("medias") or {}
    c[0].markdown(_card("Posse média", fmt(p.get("posse_pct"), "%"), f"média das competições {fmt(ref.get('posse_pct'), '%')}"), unsafe_allow_html=True)
    c[1].markdown(_card("Bolas longas nos passes", fmt(p.get("pct_bolas_longas"), "%"), f"referência {fmt(ref.get('pct_bolas_longas'), '%')}"), unsafe_allow_html=True)
    c[2].markdown(_card("Cruzamentos por jogo", fmt(p.get("cruzamentos")), f"referência {fmt(ref.get('cruzamentos'))}"), unsafe_allow_html=True)
    c[3].markdown(_card("Finalizações de dentro da área", fmt(p.get("pct_dentro_area"), "%"), f"referência {fmt(ref.get('pct_dentro_area'), '%')}"), unsafe_allow_html=True)
    if evi.get("jogos"):
        c = st.columns(4)
        c[0].markdown(_card("Desenho com bola (lances)", evi.get("desenho_com_bola") or "—",
                            f"fonte: {evi.get('desenho_fonte') or '—'} · {evi['jogos']} jogos"), unsafe_allow_html=True)
        c[1].markdown(_card("Saída com 3", f"{evi.get('saida_com_3_pct') or 0:.0f}% dos jogos", evi.get("quem_recua") or ""), unsafe_allow_html=True)
        c[2].markdown(_card("Goleiro joga longo", fmt(m.get("goleiro_longo_pct"), "%"), "passes do goleiro com 40+ jardas"), unsafe_allow_html=True)
        c[3].markdown(_card("Do fundo ao último terço", fmt(m.get("pct_fundo_ao_ultimo_terco"), "%"),
                            f"posses que nascem atrás · {fmt(m.get('passes_por_posse'))} passes por posse"), unsafe_allow_html=True)
    st.markdown("##### 🛡️ Sem a bola e transições")
    c = st.columns(4)
    c[0].markdown(_card("PPDA aproximado (estatísticas)", fmt(p.get("ppda_aprox")), f"referência {fmt(ref.get('ppda_aprox'))} · menor = pressiona mais", "#EF4444"), unsafe_allow_html=True)
    c[1].markdown(_card("xG cedido por jogo", fmt(p.get("xg_contra")), f"grandes chances cedidas {fmt(p.get('grandes_chances_contra'))}", "#EF4444"), unsafe_allow_html=True)
    if evi.get("jogos"):
        c[2].markdown(_card("PPDA real (lances)", fmt(m.get("ppda")), f"bloco a ~{fmt(m.get('altura_bloco_m'))} m do gol · {fmt(m.get('pct_acoes_def_ataque'), '%')} das ações no ataque", "#EF4444"), unsafe_allow_html=True)
        c[3].markdown(_card("Contra-ataques por jogo", f"{fmt(m.get('contra_ataques'))} feitos", f"{fmt(m.get('contra_ataques_sofridos'))} sofridos (finalização em até 15 s)", "#EF4444"), unsafe_allow_html=True)
    if evi.get("jogos") and evi.get("posicoes_ultimo_jogo"):
        ps = evi["posicoes_ultimo_jogo"]
        a, b = st.columns(2)
        if ps.get("com_bola"):
            a.plotly_chart(_pitch(ps["com_bola"]["posicoes"], f"Com bola (posições médias) · ~{ps['com_bola']['desenho']}"),
                           use_container_width=True, key=f"ti_on_{key}")
        if ps.get("sem_bola"):
            b.plotly_chart(_pitch(ps["sem_bola"]["posicoes"], f"Sem bola (ações defensivas) · ~{ps['sem_bola']['desenho']}"),
                           use_container_width=True, key=f"ti_off_{key}")
        st.caption("Campinho do jogo com lances mais recente: posição média de cada titular nas ações com bola e nas ações "
                   "defensivas (ataque para a direita). É média do jogo inteiro — não é foto de um instante.")
    if evi.get("corredores"):
        cor = pd.Series(evi["corredores"]).sort_values(ascending=False)
        st.markdown("**Por onde o time chega ao último terço (lances)** — " +
                    " · ".join(f"{k}: {v:.0f}%" for k, v in cor.items()))
    if stv.get("consistencia"):
        st.markdown("**Consistência do estilo** (aparece em quantos recortes de 3/5/10/20 jogos): " +
                    " · ".join(f"{k} — {v}" for k, v in stv["consistencia"].items()))
    rec = stv.get("recortes") or {}
    if rec:
        rows = []
        for k, lab in (("casa", "Em casa"), ("fora", "Fora"), ("vitorias", "Nas vitórias"), ("sem_vitoria", "Sem vitória")):
            r = rec.get(k) or {}
            if r.get("jogos"):
                rows.append({"Recorte": lab, "Jogos": r["jogos"], "Posse %": r.get("posse_pct"), "Bolas longas %": r.get("pct_bolas_longas"),
                             "Cruzamentos": r.get("cruzamentos"), "xG": r.get("xg"), "xG cedido": r.get("xg_contra"),
                             "PPDA aprox.": r.get("ppda_aprox")})
        if rows:
            from src.ui.components import comparison_table

            st.markdown("**O mesmo time em contextos diferentes**")
            comparison_table(pd.DataFrame(rows))
    if d.get("treinadores"):
        st.markdown("##### 🧑‍🏫 Treinadores (pela escalação da fonte)")
        for t in d["treinadores"][:4]:
            st.markdown(f"- **{t['treinador']}** — {t['jogos']} jogos ({t['de']} a {t['ate']}) · desenho mais usado "
                        f"{t.get('desenho_mais_usado') or '—'} · {t.get('pontos_por_jogo')} pontos por jogo")
    else:
        st.caption("A fonte não traz o treinador nas escalações destes jogos — sem separar períodos por técnico.")
    if d.get("contratacao"):
        st.markdown("##### 🎯 O modelo de jogo pede (contratação por função)")
        for r in d["contratacao"]:
            st.markdown(f"- **{r['funcao']}** — {r['porque']} · medir: {r['metricas']}")
    st.caption(stv.get("metodo") or "")
