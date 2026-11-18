"""Rodada 9 — "📑 Relatório da IA": tudo o que a IA do laboratório sabe sobre o jogo, num documento só."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.ui.components import comparison_table


@st.cache_data(show_spinner=False, max_entries=12)
def _report(match_id: int, focus: str, ver: str, _meta, _df, _box):
    from src.intelligence.lab_ai import engine as LAB
    from src.ui.context import get_service

    return LAB.report(_meta, _df, _box, focus, db=get_service().db)


def _ver() -> str:
    from src.intelligence.lab_ai.selector import ROOT

    p = ROOT / "registry.json"
    return str(p.stat().st_mtime) if p.exists() else "0"


def render(ctx, focus: str | None = None) -> None:
    meta = {**(ctx.bundle.meta or {}), "match_id": ctx.match_id, "data_source": ctx.bundle.source}
    with st.spinner("A IA do laboratório está montando o relatório…"):
        rep = _report(int(ctx.match_id), focus or ctx.target_team or "", _ver(), meta, ctx.df, ctx.bundle.boxscore)
    st.markdown(f"### 📑 Relatório da IA do laboratório — {rep['foco']} x {rep['rival']}")
    st.caption(f"Base: {rep['nivel']} · {rep['n_fatos']} fatos lidos · seletor v{rep['versao']:03d}. Cada número vem "
               f"direto dos dados; a régua compara com milhares de jogos da base.")
    dm = rep.get("mapa") or {}
    if dm:
        with st.expander(f"🗺️ O que este jogo tem de dado — {dm.get('rotulo')}"):
            st.markdown(" ".join(f"{'✅' if r['disponivel'] else '⛔'} {r['analise']}<br>" for r in dm["linhas"]),
                        unsafe_allow_html=True)
    if not rep["secoes"]:
        st.info("Este jogo só tem o placar — não há números para analisar.")
        return
    st.markdown("#### 🎯 Plano para explorar e corrigir")
    for x in rep["plano"] or ["Sem contraste forte o bastante nos números para um plano específico."]:
        st.markdown(f"- {x}")
    cols = st.columns(2)
    for i, sec in enumerate(rep["secoes"]):
        with cols[i % 2]:
            st.markdown(f"#### {sec['titulo']}")
            for ln in sec["linhas"]:
                st.markdown(f"- {ln}")
            if sec["leitura"]:
                st.caption("Leitura: " + sec["leitura"])
    st.markdown("#### 👤 Destaques individuais")
    pc = st.columns(max(1, len(rep["jogadores"])))
    for col, (t, lines) in zip(pc, rep["jogadores"].items()):
        col.markdown(f"**{t}**")
        for ln in lines or ["sem números por jogador nesta fonte"]:
            col.markdown(f"- {ln}")
    if rep.get("inteligencia"):
        from src.ui.pages.player_intel_view import statements_html

        st.markdown("#### 🔬 O que se destaca em cada jogador (padrão, interpretação e hipótese)")
        cols = st.columns(max(1, len(rep["inteligencia"])))
        for col, (t, players) in zip(cols, rep["inteligencia"].items()):
            with col:
                st.markdown(f"**{t}**")
                for pl in players:
                    st.markdown(f"_{pl['jogador']}_")
                    st.markdown(statements_html(pl["afirmacoes"]), unsafe_allow_html=True)
    if rep["inversoes"]:
        st.markdown("#### 🔁 Como cada time reage às inversões de jogo")
        st.caption("Inversão = passe certo que troca o corredor. Para cada uma, quem do time que defende chegou primeiro "
                   "na bola (pressão, duelo, desarme…) nos 8 s seguintes, em quanto tempo, e o que o ataque conseguiu.")
        for team, e in rep["inversoes"].items():
            st.markdown(f"**{team}** — {e['total']} inversões sofridas; em {e['sem_reacao']} ninguém chegou em 5 s"
                        + (f" (o ataque chegou ao último terço {e['avanco_sem_reacao']:.0f}% dessas vezes)"
                           if e.get("avanco_sem_reacao") is not None else "")
                        + (f"; lado mais frágil: {e['lado_mais_fragil']} do ataque rival." if e.get("lado_mais_fragil") else "."))
            if e.get("tabela"):
                comparison_table(pd.DataFrame(e["tabela"]), "Por defensor que chegou primeiro na bola.")
    with st.expander("Limites desta análise (honestidade)"):
        for x in rep["limites"]:
            st.markdown(f"- {x}")
