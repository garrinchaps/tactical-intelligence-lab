"""Página 6 — Clube: DNA longitudinal da equipe em várias partidas com eventos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data_hub.search import team_score
from src.metrics.multi_match_analyzer import MultiMatchTrendAnalyzer
from src.reports.report_builder import TacticalReportBuilder
from src.ui.components import comparison_table, empty_state, kpi, note, page_header, provenance_panel
from src.ui.context import MatchContext, get_service

MIN_TREND_MATCHES = 3


def render(ctx: MatchContext) -> None:
    page_header("📈 Clube & temporada", "Tendências da equipe em várias partidas reais com eventos (StatsBomb + Wyscout).", ctx)
    svc = get_service()
    a, b, c = st.columns([1.8, 0.7, 1.0])
    team_q = a.text_input("Clube ou seleção", value=ctx.target_team)
    n = int(b.number_input("Jogos", min_value=2, max_value=20, value=6))
    c.write("")
    run = c.button("Analisar histórico", type="primary", use_container_width=True)
    from src.ui.context import cached_catalog, filter_by_team

    cat = cached_catalog("data_level = 'EVENTS' AND data_source IN ('statsbomb','wyscout')")
    found = pd.DataFrame()
    if team_q.strip() and not cat.empty:
        found = filter_by_team(cat, team_q).sort_values("match_date", ascending=False)
        st.caption(f"{len(found)} partidas com eventos para '{team_q}'. As {min(n, len(found))} mais recentes serão usadas.")
    if not run:
        empty_state("Escolha a equipe e clique em “Analisar histórico”.", icon="📈")
        return
    if found.empty:
        empty_state("Nenhuma partida com eventos para esse time", "", "🔎", "Sincronize a competição em Catálogo & Dados.")
        return
    sel = found.head(n)
    canon = pd.concat([sel["home_team_name"], sel["away_team_name"]]).value_counts().index[0]
    events_map = {}
    prog = st.progress(0.0, text="Carregando partidas...")
    for i, mid in enumerate(sel["match_id"].tolist()):
        try:
            events_map[int(mid)] = svc.load(int(mid)).events
        except Exception as exc:
            st.caption(f"Partida {mid} indisponível: {exc}")
        prog.progress((i + 1) / len(sel), text=f"Carregando partidas... {i + 1}/{len(sel)}")
    prog.empty()
    trends = MultiMatchTrendAnalyzer.analyze_team_across_matches(events_map, target_team=canon)
    n_ok = int(trends.get("matches_analyzed", 0))
    prov = ctx.prov("club_n", f"Histórico de {canon}", n_ok, f"MultiMatchTrendAnalyzer sobre {n_ok} partidas com eventos")
    k = st.columns(3)
    with k[0]:
        kpi("partidas analisadas (n)", n_ok, prov)
    with k[1]:
        kpi("primeira", str(sel["match_date"].min())[:10], prov)
    with k[2]:
        kpi("última", str(sel["match_date"].max())[:10], prov)
    if n_ok < MIN_TREND_MATCHES:
        note("Amostra insuficiente", f"Com n = {n_ok} partidas não há tendência: os números abaixo descrevem jogos isolados.", "warn")
    if trends.get("per_match_table"):
        comparison_table(pd.DataFrame(trends["per_match_table"]), "Uma linha por partida.")
    md = TacticalReportBuilder.build_multi_match_team_history_report(trends)
    st.markdown(md)
    st.download_button(f"Baixar DNA de {canon} (.md)", data=md, file_name=f"dna_{canon.lower().replace(' ', '_')}.md",
                       mime="text/markdown")
    provenance_panel(ctx.registry)
