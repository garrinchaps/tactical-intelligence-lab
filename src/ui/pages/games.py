"""🏟️ Tela do jogo — só a partida escolhida, com "← Voltar", atalhos para os times e a competição, e as seções."""

from __future__ import annotations

import streamlit as st

from src.data_hub.registry import DataLevel
from src.ui import nav
from src.ui.components import source_gap
from src.ui.names import pt

SECTIONS = ["📊 Resumo", "🕸️ Redes & xT", "👤 Jogadores", "⚖️ Fortes e fracos", "⚔️ Duas equipes", "🧩 Padrões e histórico"]


def render(current_context, match_bar=None) -> None:
    top = st.columns([1.1, 6, 2.2])
    with top[0]:
        nav.back_button(key="game_back")
    if st.session_state.get("game_focus"):          # escolha do lado feita na rodada anterior
        st.session_state["team_focus"] = st.session_state["game_focus"]
    ctx = current_context()
    if ctx is None:
        return
    if not ctx.has_events and not st.session_state.get(f"_fm_tried_{ctx.match_id}"):
        # rodada 5: sem lances → busca NA HORA a mesma partida na FotMob (escalação, números por jogador, chutes, xG)
        st.session_state[f"_fm_tried_{ctx.match_id}"] = True
        try:
            from src.ui.context import get_service

            svc = get_service()
            box = ctx.bundle.boxscore or {}
            rich = any(getattr(box.get(k), "empty", True) is False for k in ("player_stats",))
            if svc.fotmob.enabled and not rich:
                with st.spinner("Buscando os detalhes desta partida na FotMob..."):
                    fm_id = svc.fotmob.ensure_match(int(ctx.match_id), ctx.bundle.meta or {})
                from src.ui.context import _bundle_parts

                if fm_id and fm_id != int(ctx.match_id) and svc.db.has_boxscore(fm_id):
                    st.session_state["match_id"] = int(fm_id)      # passa a mostrar a versão mais rica (FotMob)
                    st.rerun()
                elif fm_id == int(ctx.match_id):
                    _bundle_parts.clear()                          # só o cache das partidas abertas (máx. 12)
                    st.rerun()
        except Exception:
            pass
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
        from src.ui.i18n import t as _t

        if st.button(_t("💬 Perguntar sobre este jogo"), key="game_ask", use_container_width=True, type="primary"):
            st.session_state["goto"] = "assistente"
            st.rerun()
    try:                                              # B6: profundidade do dado desta partida (0 a 4)
        from src.data_hub.depth import LABELS, badge, depth_for_matches, depth_of
        from src.ui.context import get_service

        dep = depth_for_matches(get_service().db, [int(ctx.match_id)]).get(int(ctx.match_id))
        box = ctx.bundle.boxscore or {}
        has_ind = any(getattr(box.get(k), "empty", True) is False for k in ("lineups", "player_stats"))
        dep = max(dep or 0, depth_of(ctx.bundle.level, bool(box), has_ind))
        st.caption(f"{badge(dep)} — " + {0: "só o placar: sem estatísticas para analisar.",
                                         1: "estatísticas do time; sem escalação nem números por jogador.",
                                         2: "escalação e números por jogador; sem lances com coordenadas.",
                                         3: "todos os lances com coordenadas (análise completa).",
                                         4: "inclui dados físicos de tracking."}[dep]
                   + " Dado que não existe aparece como lacuna, nunca como zero.")
    except Exception:
        pass
    teams = [t for t in (h, a) if t]
    if teams:
        if st.session_state.get("game_focus") not in teams:   # outro jogo: o lado guardado não vale mais
            st.session_state["game_focus"] = ctx.target_team if ctx.target_team in teams else teams[0]
        st.radio("Analisar pelo lado de", teams, horizontal=True, key="game_focus", format_func=pt)
    from src.ui.i18n import t

    sec = st.radio("Seção", SECTIONS, horizontal=True, key="games_section", label_visibility="collapsed", format_func=t)
    from src.ui.pages import compare, match_center, networks, players, strengths

    if sec == SECTIONS[0]:
        match_center.render(ctx)
    elif sec == SECTIONS[5]:
        from src.ui.pages import patterns

        patterns.render(ctx, st.session_state.get("game_focus") or ctx.target_team)
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
