"""Página 7 — Pontos Fortes e Fracos (wrapper fino; a lógica de tela está em src/visualization/strengths_page.py)."""

from __future__ import annotations

import streamlit as st

from src.ui.components import empty_state, page_header
from src.ui.context import MatchContext, get_service
from src.visualization.strengths_page import render_strengths_weaknesses_page


@st.cache_data(show_spinner=False, ttl=3600)
def _competition_of() -> dict:
    cat = get_service().db.catalog("data_level = 'EVENTS'")
    if cat.empty:
        return {}
    return {int(r.match_id): f"{r.competition_name} {r.season_name}" for r in cat.itertuples()}


def render(ctx: MatchContext) -> None:
    page_header("⚖️ Pontos Fortes e Fracos", "Percentil contextual contra a mesma função ou contra outras equipes, com n visível.", ctx)
    if not ctx.has_events:
        empty_state("Esta partida não tem eventos", "", "⚖️", "Escolha uma partida ✅ (eventos oficiais ou simulados).")
        return
    render_strengths_weaknesses_page(ctx, get_service().db.load_events, competition_of=_competition_of())
