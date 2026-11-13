"""
TACTICAL INTELLIGENCE LAB — aplicação Streamlit.

Organização:
* barra lateral  → escolha da partida (busca universal, catálogo, arquivo) e equipe em foco;
* faixa superior → nível de dado da partida (eventos oficiais, boxscore, placar, simulado);
* navegação      → sete seções; só a seção aberta é calculada.

Execução: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Tactical Intelligence Lab",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.data_hub.registry import DataLevel  # noqa: E402
from src.ui import theme  # noqa: E402
from src.ui.components import level_banner  # noqa: E402
from src.ui.context import build_context, get_service, load_bundle, teams_of  # noqa: E402
from src.ui.match_picker import render_match_picker, render_selected_match_card  # noqa: E402
from src.ui.pages import ai_analyst, club, database, lab, match_center, players, tactics  # noqa: E402

SECTIONS = {
    "🏟️ Partida": match_center.render,
    "🧭 Tática": tactics.render,
    "👤 Jogadores": players.render,
    "📈 Clube": club.render,
    "🧠 Analista IA": ai_analyst.render,
    "🗄️ Base de Dados": database.render,
    "🎥 Laboratório": lab.render,
}
NEEDS_MATCH = {"🏟️ Partida", "🧭 Tática", "👤 Jogadores", "📈 Clube", "🧠 Analista IA"}
DEFAULT_MATCH_ID = 3869685  # final da Copa do Mundo 2022 (StatsBomb), já incluída no banco


def main() -> None:
    theme.inject_theme()
    st.session_state.setdefault("match_id", DEFAULT_MATCH_ID)
    st.session_state.setdefault("chat_history", [])
    service = get_service()

    render_match_picker(service)

    section = st.radio("Navegação", list(SECTIONS.keys()), horizontal=True, label_visibility="collapsed",
                       key="nav_section")

    if section not in NEEDS_MATCH:
        SECTIONS[section](None)
        return

    try:
        with st.spinner("Carregando partida..."):
            bundle = load_bundle(int(st.session_state["match_id"]))
    except Exception as exc:
        st.error(f"Não foi possível abrir a partida {st.session_state['match_id']}: {exc}")
        st.info("Escolha outra partida na barra lateral ou sincronize a base em 🗄️ Base de Dados.")
        return

    upload_df = st.session_state.get("upload_df") if bundle.level == DataLevel.UPLOAD else None
    teams = teams_of(bundle, upload_df if upload_df is not None else bundle.events)
    team = render_selected_match_card(bundle, teams, st.session_state.get("team_focus"))
    st.session_state["team_focus"] = team

    level_banner(bundle.level, bundle.source_label)
    try:
        ctx = build_context(bundle, team, upload_df=upload_df)
    except Exception as exc:
        st.error(f"Erro ao processar a partida: {exc}")
        return
    SECTIONS[section](ctx)


if __name__ == "__main__":
    main()
