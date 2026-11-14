"""🏟️ Jogos — pesquisa de partidas (todas as fontes) e análise completa da partida escolhida."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data_hub.registry import BADGES, DataLevel
from src.ui.components import empty_state, hero, result_card_html

LEVEL_ORDER = {DataLevel.EVENTS: 0, DataLevel.BOXSCORE: 1, DataLevel.RESULT: 2, DataLevel.SIMULATED: 3, DataLevel.UPLOAD: 4}
SECTIONS = ["📊 Resumo", "🕸️ Redes & xT", "👤 Jogadores", "⚖️ Fortes e fracos", "⚔️ Duas equipes"]


def _search(q: str, genero: str, nivel: str, limit: int = 24) -> pd.DataFrame:
    from src.data_hub.gender import gender_series
    from src.ui.context import cached_catalog, filter_by_team, get_service

    cat = cached_catalog()
    if cat.empty:
        return cat
    out = pd.DataFrame()
    if q.strip():
        try:
            res = get_service().finder.find(q, allow_remote=st.session_state.get("games_remote", False))
            out = res["candidates"] if not res["candidates"].empty else res.get("suggestions", pd.DataFrame())
            for n in res.get("notes", [])[:2]:
                st.caption(f"ℹ️ {n}")
        except Exception:
            out = pd.DataFrame()
        if out is None or out.empty:                         # nome de time ou competição solto
            out = filter_by_team(cat, q, 0.86)
            if out.empty:
                out = cat[cat["competition_name"].str.contains(q, case=False, regex=False, na=False)]
    else:
        out = cat[cat["data_level"] == DataLevel.EVENTS].head(200)
    if out is None or out.empty:
        return pd.DataFrame()
    if "genero" not in out:
        out = out.assign(genero=gender_series(out))
    if genero != "todos":
        out = out[out["genero"] == genero]
    if nivel != "todos":
        out = out[out["data_level"] == nivel]
    out = out.assign(_lv=out["data_level"].map(LEVEL_ORDER).fillna(9))
    return out.sort_values(["match_date", "_lv"], ascending=[False, True]).drop_duplicates("match_id").head(limit)


def _results(found: pd.DataFrame) -> None:
    for i, m in enumerate(found.to_dict("records")):
        a, b = st.columns([8, 1.2])
        a.markdown(result_card_html(m, BADGES.get(m.get("data_level"), m.get("data_level", ""))), unsafe_allow_html=True)
        b.write("")
        if b.button("Abrir", key=f"open_{m['match_id']}_{i}", use_container_width=True,
                    type="primary" if int(m["match_id"]) == int(st.session_state.get("match_id", 0)) else "secondary"):
            st.session_state["match_id"] = int(m["match_id"])
            st.session_state["team_focus"] = None
            st.session_state["chat_history"] = []
            st.session_state["games_section"] = SECTIONS[0]
            st.rerun()


def render(current_context, match_bar) -> None:
    hero("Jogos", "Pesquise qualquer partida",
         "Mais de 150 mil jogos de StatsBomb, Wyscout, openfootball, football-data.co.uk, seleções desde 1872, "
         "API-Football e ESPN. ✅ = eventos com coordenadas (análise completa) · 📊 = estatísticas e escalações · 📄 = placar.")
    pre = st.session_state.pop("search_from_top", None)
    if pre:
        st.session_state["games_q"] = pre
    a, b, c, d = st.columns([3.2, 1.2, 1.4, 1.0])
    q = a.text_input("Partida", key="games_q", placeholder="ex.: Flamengo x Palmeiras 2026 · Argentina x França 2022 · Leverkusen")
    genero = b.selectbox("Futebol", ["masculino", "feminino", "todos"], key="games_gen")
    nivel = c.selectbox("Nível", ["todos", DataLevel.EVENTS, DataLevel.BOXSCORE, DataLevel.RESULT], key="games_lvl",
                        format_func=lambda x: "todos os níveis" if x == "todos" else BADGES.get(x, x))
    d.write("")
    st.session_state["games_remote"] = d.toggle("Online", value=False, help="Consultar também as APIs online (jogos de hoje/ontem).")
    with st.spinner("Procurando..."):
        found = _search(q, genero, nivel)
    left, right = st.columns([1.05, 1.95])
    with left:
        st.markdown(f"##### {len(found)} partida(s)" if not found.empty else "##### Nenhuma partida")
        if found.empty:
            empty_state("Nada encontrado", "Tente o nome dos times, a competição ou o ano.", "🔎")
        else:
            _results(found)
    with right:
        match_bar()
        ctx = current_context()
        if ctx is None:
            return
        sec = st.radio("Seção", SECTIONS, horizontal=True, key="games_section", label_visibility="collapsed")
        from src.ui.pages import compare, match_center, networks, players, strengths

        if sec == SECTIONS[0]:
            match_center.render(ctx)
        elif not ctx.has_events and sec != SECTIONS[2]:
            empty_state("Esta seção precisa de eventos com coordenadas", f"A partida tem nível {BADGES.get(ctx.bundle.level)}.",
                        "🗺️", "Abra uma partida ✅ (StatsBomb/Wyscout) para redes, xT e comparações espaciais.")
        elif sec == SECTIONS[1]:
            networks.render(ctx)
        elif sec == SECTIONS[2]:
            players.render(ctx)
        elif sec == SECTIONS[3]:
            strengths.render(ctx)
        else:
            compare._two_teams(ctx)
