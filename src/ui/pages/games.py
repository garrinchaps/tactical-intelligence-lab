"""🏟️ Tela do jogo — só a partida escolhida, com "← Voltar", atalhos para os times e a competição, e as seções."""

from __future__ import annotations

import streamlit as st

from src.data_hub.registry import DataLevel
from src.ui import nav
from src.ui.components import source_gap
from src.ui.names import pt

SECTIONS = ["📊 Resumo", "🕸️ Redes & xT", "👤 Jogadores", "⚖️ Fortes e fracos", "⚔️ Duas equipes"]


def render(current_context, match_bar=None) -> None:
    top = st.columns([1.1, 6, 2.2])
    with top[0]:
        nav.back_button(key="game_back")
    if st.session_state.get("game_focus"):          # escolha do lado feita na rodada anterior
        st.session_state["team_focus"] = st.session_state["game_focus"]
    ctx = current_context()
    if ctx is None:
        return
    meta = ctx.bundle.meta or {}
    h, a = meta.get("home_team_name", ""), meta.get("away_team_name", "")
    comp, season = meta.get("competition_name", ""), meta.get("season_name", "")
    with top[1]:
        c1, c2, c3 = st.columns(3)
        with c1:
            nav.link(f"🛡️ {pt(h)}", "time", key="game_team_h", name=h)
        with c2:
            nav.link(f"🛡️ {pt(a)}", "time", key="game_team_a", name=a)
        with c3:
            if comp:
                nav.link(f"🏆 {comp}", "competicao", key="game_comp", name=comp, season=season)
    with top[2]:
        if st.button("💬 Perguntar sobre este jogo", key="game_ask", use_container_width=True, type="primary"):
            st.session_state["goto"] = "assistente"
            st.rerun()
    teams = [t for t in (h, a) if t]
    if teams:
        if st.session_state.get("game_focus") not in teams:   # outro jogo: o lado guardado não vale mais
            st.session_state["game_focus"] = ctx.target_team if ctx.target_team in teams else teams[0]
        st.radio("Analisar pelo lado de", teams, horizontal=True, key="game_focus", format_func=pt)
    sec = st.radio("Seção", SECTIONS, horizontal=True, key="games_section", label_visibility="collapsed")
    from src.ui.pages import compare, match_center, networks, players, strengths

    if sec == SECTIONS[0]:
        match_center.render(ctx)
    elif not ctx.has_events and sec != SECTIONS[2]:
        source_gap("eventos com coordenadas", ctx.bundle.source,
                   "Redes de passe, xT e comparações espaciais precisam de jogos ✅ (StatsBomb/Wyscout).", "🗺️",
                   ctx.bundle.level)
    elif sec == SECTIONS[1]:
        networks.render(ctx)
    elif sec == SECTIONS[2]:
        players.render(ctx)
    elif sec == SECTIONS[3]:
        strengths.render(ctx)
    else:
        compare._two_teams(ctx)


def is_analyzable(level: str) -> bool:
    return level in DataLevel.ANALYZABLE
