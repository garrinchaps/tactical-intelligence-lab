"""Seção 📈 Clube — DNA longitudinal da equipe em várias partidas com eventos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data_hub.search import team_score
from src.metrics.multi_match_analyzer import MultiMatchTrendAnalyzer
from src.reports.report_builder import TacticalReportBuilder
from src.ui.components import section_header
from src.ui.context import MatchContext, get_service


def render(ctx: MatchContext) -> None:
    section_header("📈 Clube & temporada",
                   "Tendências crônicas da equipe em várias partidas reais com eventos (StatsBomb + Wyscout).")
    svc = get_service()
    a, b, c = st.columns([1.8, 0.7, 1.0])
    team_q = a.text_input("Clube ou seleção", value=ctx.target_team)
    n = int(b.number_input("Jogos", min_value=2, max_value=20, value=6))
    c.write("")
    run = c.button("Analisar histórico", type="primary", use_container_width=True)
    cat = svc.db.catalog("data_level = 'EVENTS' AND data_source IN ('statsbomb','wyscout')")
    if team_q.strip() and not cat.empty:
        cat = cat.copy()
        cat["s"] = cat.apply(lambda r: max(team_score(team_q, r["home_team_name"]),
                                           team_score(team_q, r["away_team_name"])), axis=1)
        found = cat[cat["s"] >= 0.86].sort_values("match_date", ascending=False)
        st.caption(f"{len(found)} partidas com eventos encontradas para '{team_q}'. As {min(n, len(found))} mais recentes serão usadas.")
    else:
        found = pd.DataFrame()
    if not run:
        return
    if found.empty:
        st.warning("Nenhuma partida com eventos para esse time. Sincronize a base ou tente outro nome.")
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
    md = TacticalReportBuilder.build_multi_match_team_history_report(trends)
    st.success(f"{canon}: {trends.get('matches_analyzed', 0)} partidas analisadas.")
    if trends.get("per_match_table"):
        st.dataframe(pd.DataFrame(trends["per_match_table"]), use_container_width=True, hide_index=True)
    st.markdown(md)
    st.download_button(f"Baixar DNA de {canon} (.md)", data=md,
                       file_name=f"dna_{canon.lower().replace(' ', '_')}.md", mime="text/markdown")
