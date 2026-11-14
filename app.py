"""
TACTICAL INTELLIGENCE LAB — aplicação Streamlit.

Organização (navegação lateral agrupada, st.navigation):
  Partida ............ 1 Centro da Partida · 2 Redes de Passes & xT
  Inteligência Artificial  3 Machine Learning & Inspeção · 4 Rede Neural do Zero · 8 Analista IA
  Jogadores, Clube e Comparações  Comparações · 5 Jogadores · 6 Clube · 7 Pontos Fortes e Fracos
  Dados .............. 9 Catálogo & Dados · Laboratório

Cada página recebe o mesmo MatchContext (partida, equipe em foco, registro de proveniência) e só ela é
calculada quando aberta. Execução: streamlit run app.py
"""

from __future__ import annotations

from typing import Callable

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Tactical Intelligence Lab", page_icon="⚽", layout="wide", initial_sidebar_state="expanded")

from src.data_hub.registry import DataLevel  # noqa: E402
from src.ui import theme  # noqa: E402
from src.ui.components import empty_state, error_state, level_banner  # noqa: E402
from src.ui.context import build_context, get_service, load_bundle, teams_of  # noqa: E402
from src.ui.match_picker import render_match_picker, render_selected_match_card  # noqa: E402
from src.ui.pages import (ai_analyst, catalog, club, compare, lab, match_center, ml_inspection, networks,  # noqa: E402
                          neural, players, strengths)

DEFAULT_MATCH_ID = 3869685  # final da Copa do Mundo 2022 (StatsBomb) — também disponível offline em data/demo


def _context():
    """Abre a partida escolhida e monta o contexto. Devolve None (com estado de erro desenhado) se falhar."""
    try:
        with st.spinner("Carregando partida..."):
            bundle = load_bundle(int(st.session_state["match_id"]))
    except Exception as exc:
        error_state(f"Não foi possível abrir a partida {st.session_state['match_id']}", exc,
                    "Escolha outra partida na barra lateral ou sincronize a base em Catálogo & Dados.")
        return None
    upload_df = st.session_state.get("upload_df") if bundle.level == DataLevel.UPLOAD else None
    teams = teams_of(bundle, upload_df if upload_df is not None else bundle.events)
    team = render_selected_match_card(bundle, teams, st.session_state.get("team_focus"))
    st.session_state["team_focus"] = team
    level_banner(bundle.level, bundle.source_label)
    try:
        return build_context(bundle, team, upload_df=upload_df)
    except Exception as exc:
        error_state("Erro ao processar a partida", exc)
        return None


def _with_match(render: Callable, needs_events: bool = False) -> Callable[[], None]:
    def page() -> None:
        ctx = _context()
        if ctx is None:
            return
        if needs_events and not ctx.has_events:
            empty_state("Esta página precisa de eventos com coordenadas", f"A partida aberta tem nível {ctx.bundle.level}.",
                        "🗺️", "Escolha uma partida marcada com ✅ (eventos oficiais) na barra lateral.")
            return
        render(ctx)
    page.__name__ = f"page_{render.__module__.rsplit('.', 1)[-1]}"
    return page


def _with_optional_match(render: Callable) -> Callable[[], None]:
    """Páginas que funcionam sem partida (rede neural): usam o contexto se ele abrir."""
    def page() -> None:
        ctx = None
        try:
            ctx = build_context(load_bundle(int(st.session_state["match_id"])), st.session_state.get("team_focus"),
                                with_sim_ci=False)
        except Exception:
            ctx = None
        render(ctx)
    page.__name__ = f"page_{render.__module__.rsplit('.', 1)[-1]}"
    return page


def _standalone(render: Callable) -> Callable[[], None]:
    def page() -> None:
        render(None)
    page.__name__ = f"page_{render.__module__.rsplit('.', 1)[-1]}"
    return page


PAGES = {
    "Partida": [
        st.Page(_with_match(match_center.render), title="Centro da Partida", icon="🏟️", url_path="partida", default=True),
        st.Page(_with_match(networks.render, needs_events=True), title="Redes de Passes & xT", icon="🕸️", url_path="redes"),
    ],
    "Inteligência Artificial": [
        st.Page(_with_match(ml_inspection.render), title="Machine Learning & Inspeção", icon="🤖", url_path="ml"),
        st.Page(_with_optional_match(neural.render), title="Rede Neural do Zero", icon="🧠", url_path="rede-neural"),
        st.Page(_with_match(ai_analyst.render), title="Analista IA", icon="💬", url_path="analista"),
    ],
    "Jogadores, Clube e Comparações": [
        st.Page(_with_match(compare.render, needs_events=True), title="Comparações", icon="🆚", url_path="comparacoes"),
        st.Page(_with_match(players.render), title="Jogadores", icon="👤", url_path="jogadores"),
        st.Page(_with_match(club.render), title="Clube & Temporada", icon="📈", url_path="clube"),
        st.Page(_with_match(strengths.render), title="Pontos Fortes e Fracos", icon="⚖️", url_path="fortes-fracos"),
    ],
    "Dados": [
        st.Page(_standalone(catalog.render), title="Catálogo & Dados", icon="🗄️", url_path="dados"),
        st.Page(_standalone(lab.render), title="Laboratório", icon="🧪", url_path="laboratorio"),
    ],
}


def main() -> None:
    theme.inject_theme()
    st.session_state.setdefault("match_id", DEFAULT_MATCH_ID)
    st.session_state.setdefault("chat_history", [])
    nav = st.navigation(PAGES, position="sidebar")
    render_match_picker(get_service())
    try:
        from src.data_hub import autosync

        st.sidebar.caption(autosync.status_text(autosync.ensure_started(get_service().db)))
    except Exception as exc:  # a atualização automática nunca impede o app de abrir
        st.sidebar.caption(f"Atualização automática indisponível: {exc}")
    nav.run()


main()
