"""🏟️ Tela do jogo — só a partida escolhida, com "← Voltar", atalhos para os times e a competição, e as seções."""

from __future__ import annotations

import streamlit as st

from src.data_hub.registry import DataLevel
from src.ui import nav
from src.ui.components import source_gap
from src.ui.names import pt

SECTIONS = ["📊 Resumo", "🕸️ Redes & xT", "👤 Jogadores", "⚖️ Fortes e fracos", "⚔️ Duas equipes", "🧩 Padrões e histórico"]
BOTH = "⚖️ Os dois times"


def _swap(ctx):
    """Mesmo jogo pelo outro lado (para analisar os dois times de uma vez)."""
    import dataclasses

    return dataclasses.replace(ctx, target_team=ctx.opponent, opponent=ctx.target_team,
                               summary=ctx.opp_summary, opp_summary=ctx.summary)


def _lazy(label: str, key: str) -> bool:
    """Seções pesadas da IA só calculam quando o usuário abre (a página do jogo abre na hora)."""
    return st.toggle(label, key=key, value=False)


def render(current_context, match_bar=None) -> None:
    top = st.columns([1.1, 6, 2.2])
    with top[0]:
        nav.back_button(key="game_back")
    if st.session_state.get("game_focus") and st.session_state["game_focus"] != BOTH:   # lado escolhido antes
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

        if st.button(_t("💬 Perguntar sobre este jogo"), key="game_ask", width="stretch", type="primary"):
            st.session_state["goto"] = "assistente"
            st.rerun()
    try:                                              # B6: profundidade do dado desta partida (0 a 4)
        from src.data_hub.depth import LABELS, badge, depth_for_matches, depth_of
        from src.ui.context import get_service

        dep_db = depth_for_matches(get_service().db, [int(ctx.match_id)]).get(int(ctx.match_id))
        box = ctx.bundle.boxscore or {}
        team_stats = box.get("team_stats")
        has_team = getattr(team_stats, "empty", True) is False
        has_ind = any(getattr(box.get(k), "empty", True) is False for k in ("lineups", "player_stats"))
        # Não usar bool(box): o dicionário tem as chaves mesmo quando todos os DataFrames estão vazios.
        # O selo precisa refletir conteúdo real, não apenas a existência do contêiner de boxscore.
        dep_loaded = depth_of(ctx.bundle.level, has_team_stats=has_team, has_individual=has_ind)
        dep = max(dep_db or 0, dep_loaded)
        st.caption(f"{badge(dep)} — " + {0: "nenhuma das nossas bases (FotMob, ESPN, StatsBomb, Wyscout, OpenPlay, API-Football…) achou estatísticas desta partida — só o placar.",
                                         1: "estatísticas do time; sem escalação nem números por jogador.",
                                         2: "escalação e números por jogador; sem lances com coordenadas.",
                                         3: "todos os lances com coordenadas (análise completa).",
                                         4: "inclui dados físicos de tracking."}[dep]
                   + " Dado que não existe aparece como lacuna, nunca como zero.")
    except Exception:
        pass
    teams = [t for t in (h, a) if t]
    if teams:
        opts = teams + ([BOTH] if len(teams) == 2 else [])
        if st.session_state.get("game_focus") not in opts:    # outro jogo: o lado guardado não vale mais
            st.session_state["game_focus"] = ctx.target_team if ctx.target_team in teams else teams[0]
        st.radio("Analisar pelo lado de", opts, horizontal=True, key="game_focus",
                 format_func=lambda x: x if x == BOTH else pt(x))
    both = st.session_state.get("game_focus") == BOTH
    focus_team = ctx.target_team if both else (st.session_state.get("game_focus") or ctx.target_team)
    sides = [(ctx.target_team, ctx), (ctx.opponent, _swap(ctx))] if both and ctx.opponent else [(focus_team, ctx)]
    from src.ui.i18n import t

    sec = st.radio("Seção", SECTIONS, horizontal=True, key="games_section", label_visibility="collapsed", format_func=t)
    from src.ui.pages import compare, match_center, networks, players, strengths

    def each(fn):
        for i, (team, c) in enumerate(sides):
            if both:
                st.markdown(f"## {'🔵' if i == 0 else '🔴'} {pt(team)}")
            fn(team, c, i)
            if both and i == 0:
                st.markdown("---")

    if sec == SECTIONS[0]:
        match_center.render(ctx)
    elif sec == SECTIONS[5]:
        from src.ui.pages import patterns

        each(lambda team, c, i: patterns.render(c, team, kp=str(i)))
        # rodada 13: o antigo "📑 Relatório da IA" virou parte dos padrões (abre sob demanda)
        if _lazy("📑 Relatório completo da IA do laboratório (plano, fases, destaques)", f"lab_rep_{ctx.match_id}"):
            from src.ui.pages import lab_report

            for team, c in sides:
                lab_report.render(c, team)
    elif sec == SECTIONS[1]:
        if ctx.has_events:
            networks.render(ctx)
            # rodada 13: o antigo "🧠 Perigo (IA)" fica junto da leitura de ameaça (xT)
            st.markdown("---")
            if _lazy("🧠 Perigo de cada ação pela rede neural (chance de a posse terminar em chute)", f"danger_{ctx.match_id}"):
                from src.ui.pages import danger_view

                danger_view.render(ctx, focus_team)
        else:
            from src.ui.pages import fotmob_depth

            fotmob_depth.render(ctx)                 # rodada 5: momentum, corredores, xG acumulado, destaques (FotMob)
    elif sec == SECTIONS[3]:
        if ctx.has_events:
            each(lambda team, c, i: strengths.render(c))
        else:
            from src.ui.pages import fotmob_strengths

            each(lambda team, c, i: fotmob_strengths.render(c, team))
    elif sec == SECTIONS[2]:
        players.render(ctx)
        # rodada 13: o antigo "🔬 Jogador (IA)" fica na aba dos jogadores
        st.markdown("---")
        if _lazy("🔬 Leitura de um jogador pela IA (lance, partida ou vários jogos)", f"pintel_{ctx.match_id}"):
            from src.ui.pages import player_intel_view

            player_intel_view.render(ctx, focus_team)
    elif not ctx.has_events:
        source_gap("eventos com coordenadas", ctx.bundle.source,
                   "Comparações espaciais precisam de jogos ✅ (StatsBomb/Wyscout/OpenPlay).", "🗺️",
                   ctx.bundle.level)
    else:
        compare._two_teams(ctx)


def is_analyzable(level: str) -> bool:
    return level in DataLevel.ANALYZABLE
