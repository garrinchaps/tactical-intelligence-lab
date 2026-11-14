"""
TACTICAL INTELLIGENCE LAB — aplicação Streamlit.

Navegação no topo (pílulas) + busca global + faixa da partida aberta:
  💬 Assistente (chat único: a pergunta pode trazer o jogo junto) · 🏟️ Jogos · 🛡️ Clubes · 👤 Jogadores · 🆚 Comparar
  ⚙️ Bastidores (separado do programa): como a IA aprende, ML & avaliação, analista técnico, dados & fontes, laboratório

Execução: streamlit run app.py
"""

from __future__ import annotations

from typing import Callable

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Tactical Intelligence Lab", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")

from src.data_hub.registry import BADGES, DataLevel  # noqa: E402
from src.ui import theme  # noqa: E402
from src.ui.components import empty_state, error_state, match_strip  # noqa: E402
from src.ui.context import build_context, get_service, load_bundle, teams_of  # noqa: E402
from src.ui.match_picker import render_match_picker  # noqa: E402
from src.ui.pages import (ai_analyst, assistant, catalog, clubs, compare, games, lab, ml_inspection,  # noqa: E402
                          neural, players_search)

DEFAULT_MATCH_ID = 3869685  # final da Copa do Mundo 2022 (StatsBomb) — disponível offline em data/demo


# ------------------------------------------------------------------ contexto da partida
def current_context(with_sim_ci: bool = True):
    """Abre a partida da sessão e monta o contexto (None + estado de erro desenhado se falhar)."""
    try:
        bundle = load_bundle(int(st.session_state["match_id"]))
    except Exception as exc:
        error_state(f"Não foi possível abrir a partida {st.session_state['match_id']}", exc,
                    "Use “Trocar partida” no topo ou sincronize a base em Bastidores → Dados & Fontes.")
        return None
    upload_df = st.session_state.get("upload_df") if bundle.level == DataLevel.UPLOAD else None
    teams = teams_of(bundle, upload_df if upload_df is not None else bundle.events)
    if st.session_state.get("team_focus") not in teams and teams:
        st.session_state["team_focus"] = teams[0]
    try:
        return build_context(bundle, st.session_state.get("team_focus"), upload_df=upload_df, with_sim_ci=with_sim_ci)
    except Exception as exc:
        error_state("Erro ao processar a partida", exc)
        return None


def match_bar() -> None:
    """Faixa da partida aberta + equipe em foco + painel para trocar de partida."""
    try:
        bundle = load_bundle(int(st.session_state["match_id"]))
    except Exception:
        bundle = None
    a, b, c = st.columns([5.2, 2.4, 1.4])
    with a:
        if bundle is not None:
            match_strip(bundle.meta or {}, BADGES.get(bundle.level, bundle.level))
    with b:
        if bundle is not None:
            teams = teams_of(bundle, bundle.events)
            if teams:
                cur = st.session_state.get("team_focus")
                st.session_state["team_focus"] = st.radio("Equipe em foco", teams, index=teams.index(cur) if cur in teams else 0,
                                                          horizontal=True, key="team_focus_radio", label_visibility="collapsed")
    with c:
        with st.popover("🔄 Trocar partida", use_container_width=True):
            render_match_picker(get_service())


def needs_match(render: Callable, needs_events: bool = False) -> Callable[[], None]:
    def page() -> None:
        match_bar()
        ctx = current_context()
        if ctx is None:
            return
        if needs_events and not ctx.has_events:
            empty_state("Esta seção precisa de eventos com coordenadas", f"A partida aberta tem nível {ctx.bundle.level}.",
                        "🗺️", "Troque para uma partida ✅ (eventos StatsBomb/Wyscout).")
            return
        render(ctx)
    page.__name__ = f"page_{render.__module__.rsplit('.', 1)[-1]}"
    return page


def standalone(render: Callable, pass_ctx: bool = False) -> Callable[[], None]:
    def page() -> None:
        render(current_context(with_sim_ci=False) if pass_ctx else None)
    page.__name__ = f"page_{render.__module__.rsplit('.', 1)[-1]}"
    return page


def _named(fn: Callable, name: str) -> Callable:
    fn.__name__ = name
    return fn


MAIN = [
    st.Page(_named(lambda: assistant.render(current_context, match_bar), "page_assistente"), title="Assistente", icon="💬",
            url_path="assistente", default=True),
    st.Page(_named(lambda: games.render(current_context, match_bar), "page_jogos"), title="Jogos", icon="🏟️", url_path="jogos"),
    st.Page(standalone(clubs.render), title="Clubes", icon="🛡️", url_path="clubes"),
    st.Page(standalone(players_search.render), title="Jogadores", icon="👤", url_path="jogadores"),
    st.Page(_named(lambda: compare.render_page(current_context, match_bar), "page_comparar"), title="Comparar", icon="🆚",
            url_path="comparar"),
]
BACKSTAGE = [
    st.Page(standalone(neural.render, pass_ctx=True), title="Como a IA aprende", icon="🧠", url_path="como-a-ia-aprende"),
    st.Page(needs_match(ml_inspection.render), title="Machine Learning & Avaliação", icon="🤖", url_path="ml"),
    st.Page(needs_match(ai_analyst.render), title="Analista técnico (guard)", icon="🛡️", url_path="analista-tecnico"),
    st.Page(standalone(catalog.render), title="Dados & Fontes", icon="🗄️", url_path="dados"),
    st.Page(standalone(lab.render), title="Laboratório", icon="🧪", url_path="laboratorio"),
]


def top_bar() -> None:
    """Logo + navegação em pílulas + Bastidores + busca global."""
    cols = st.columns([2.3] + [1.15] * len(MAIN) + [1.35])
    cols[0].markdown('<div style="font-family:Space Grotesk,sans-serif;font-weight:700;font-size:1.18rem;line-height:2.4rem">'
                     '⚽ Tactical <span style="background:var(--til-grad);-webkit-background-clip:text;color:transparent">'
                     'Intelligence</span> Lab</div>', unsafe_allow_html=True)
    for col, page in zip(cols[1:], MAIN):
        col.page_link(page, label=page.title, icon=page.icon, use_container_width=True)
    with cols[-1].popover("⚙️ Bastidores", use_container_width=True):
        st.caption("Como tudo foi feito — separado do programa.")
        for page in BACKSTAGE:
            st.page_link(page, label=page.title, icon=page.icon)
    q1, q2 = st.columns([6, 1])
    q = q1.text_input("Busca", placeholder="🔎  Busque um jogo, clube ou jogador — ex.: Flamengo x Palmeiras, Leverkusen, Messi",
                      label_visibility="collapsed", key="global_q")
    if q2.button("Buscar", type="primary", use_container_width=True) and q.strip():
        st.session_state["search_from_top"] = q.strip()
        st.switch_page(MAIN[1])
    st.markdown('<div class="til-glow"></div>', unsafe_allow_html=True)


def main() -> None:
    theme.inject_theme()
    st.session_state.setdefault("match_id", DEFAULT_MATCH_ID)
    st.session_state.setdefault("chat_history", [])
    nav = st.navigation(MAIN + BACKSTAGE, position="hidden")
    goto = st.session_state.pop("goto", None)            # outras páginas pedem para abrir a partida em Jogos
    if goto:
        st.switch_page({"jogos": MAIN[1], "assistente": MAIN[0], "comparar": MAIN[4]}.get(goto, MAIN[1]))
    top_bar()
    try:
        from src.data_hub import autosync

        st.caption(autosync.status_text(autosync.ensure_started(get_service().db)))
    except Exception:
        pass
    nav.run()


main()
