"""
Barra lateral: escolha da partida.

1. Busca universal (texto livre: times, datas, "ontem", ID...).
2. Catálogo navegável com filtros (fonte, nível de dado, competição, temporada, time).
3. Upload de arquivo de eventos.
A partida escolhida fica em st.session_state["match_id"].
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from src.data_hub.registry import BADGES, SOURCES, DataLevel
from src.data_hub.service import MatchDataService

LEVEL_ICON = {DataLevel.EVENTS: "✅", DataLevel.BOXSCORE: "📊", DataLevel.RESULT: "📄",
              DataLevel.SIMULATED: "⚠️", DataLevel.UPLOAD: "📁"}


def match_label(r) -> str:
    g = lambda k: (r.get(k) if isinstance(r, dict) else getattr(r, k, None))
    hs, as_ = g("home_score"), g("away_score")
    score = f"{int(hs)}–{int(as_)}" if pd.notna(hs) and pd.notna(as_) and hs is not None else "x"
    return (f"{LEVEL_ICON.get(g('data_level'), '•')} {g('home_team_name')} {score} {g('away_team_name')} · "
            f"{g('competition_name')} · {g('match_date') or '?'}")


def _select(service: MatchDataService, match_id: int) -> None:
    st.session_state["match_id"] = int(match_id)
    st.session_state["chat_history"] = []
    st.session_state.pop("upload_df", None)


def render_match_picker(service: MatchDataService, box=None) -> None:
    """Busca/catálogo/arquivo para escolher a partida. `box` = onde desenhar (painel do topo; antes era a barra lateral)."""
    box = box if box is not None else st
    from src.data_hub.gender import LABELS, gender_of

    genero = box.radio("Futebol", ["masculino", "feminino", "todos"], horizontal=True, key="genero",
                              format_func=lambda g: LABELS[g],
                              help="Separa as competições masculinas e femininas na busca e no catálogo.")

    def by_gender(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or genero == "todos":
            return df
        g = df["genero"] if "genero" in df.columns else pd.Series([gender_of(r) for r in df.to_dict("records")], index=df.index)
        return df[g == genero]

    tab_search, tab_catalog, tab_upload = box.tabs(["🔎 Buscar", "📚 Catálogo", "📁 Arquivo"])

    with tab_search:
        query = st.text_input(
            "Confronto, time, data ou ID",
            value=st.session_state.get("last_query", ""),
            placeholder="ex.: Argentina x França 2022, Leverkusen, Flamengo x Palmeiras ontem",
            key="search_query",
        )
        allow_remote = st.checkbox("Buscar também nas fontes online", value=True,
                                   help="Usa API-Football, ESPN e football-data.org quando habilitadas no .env.")
        if st.button("Buscar partida", type="primary", use_container_width=True) and query.strip():
            with st.spinner("Procurando em todas as fontes..."):
                st.session_state["last_query"] = query
                st.session_state["search_result"] = service.finder.find(query, allow_remote=allow_remote)

        res = st.session_state.get("search_result")
        if res:
            for n in res.get("notes", []):
                st.caption(f"ℹ️ {n}")
            cands = res["candidates"] if not res["candidates"].empty else res.get("suggestions", pd.DataFrame())
            all_n = 0 if cands is None else len(cands)
            cands = by_gender(cands)
            if all_n and (cands is None or cands.empty):
                st.caption(f"ℹ️ {all_n} resultado(s) no futebol {'feminino' if genero == 'masculino' else 'masculino'}: "
                           "troque o filtro “Futebol” acima para vê-los.")
            if cands is not None and not cands.empty:
                options = {match_label(r): int(r["match_id"]) for _, r in cands.iterrows()}
                choice = st.radio("Resultados", list(options.keys()), key="search_choice")
                if st.button("Abrir esta partida", use_container_width=True):
                    _select(service, options[choice])
                    st.rerun()

    with tab_catalog:
        from src.ui.context import cached_catalog

        cat = by_gender(cached_catalog())
        if cat.empty:
            st.info("Catálogo vazio. Sincronize a base na página 🗄️ Catálogo & Dados.")
        else:
            src_opts = ["Todas"] + sorted(cat["data_source"].dropna().unique().tolist())
            src = st.selectbox("Fonte", src_opts, format_func=lambda s: SOURCES[s].label if s in SOURCES else s)
            lvl = st.selectbox("Nível de dado", ["Todos"] + list(DataLevel.ALL),
                               format_func=lambda l: BADGES.get(l, l))
            f = cat
            if src != "Todas":
                f = f[f["data_source"] == src]
            if lvl != "Todos":
                f = f[f["data_level"] == lvl]
            comps = ["Todas"] + sorted(f["competition_name"].dropna().unique().tolist())
            comp = st.selectbox("Competição", comps)
            if comp != "Todas":
                f = f[f["competition_name"] == comp]
                seasons = ["Todas"] + sorted(f["season_name"].dropna().unique().tolist(), reverse=True)
                season = st.selectbox("Temporada", seasons)
                if season != "Todas":
                    f = f[f["season_name"] == season]
            team = st.text_input("Filtrar por time", "")
            if team.strip():
                t = team.strip().lower()
                f = f[f["home_team_name"].str.lower().str.contains(t, na=False) |
                      f["away_team_name"].str.lower().str.contains(t, na=False)]
            st.caption(f"{len(f)} partidas")
            f = f.head(300)
            if not f.empty:
                options = {match_label(r): int(r["match_id"]) for _, r in f.iterrows()}
                choice = st.selectbox("Partida", list(options.keys()), key="catalog_choice")
                if st.button("Abrir partida do catálogo", use_container_width=True):
                    _select(service, options[choice])
                    st.rerun()

    with tab_upload:
        uploaded = st.file_uploader("Eventos (.csv ou .json, formato StatsBomb)", type=["csv", "json"])
        if uploaded is not None and st.button("Carregar arquivo", use_container_width=True):
            try:
                from src.ingestion.statsbomb_loader import StatsBombDataLoader

                tmp = Path("data/raw") / f"uploaded_{uploaded.name}"
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_bytes(uploaded.getvalue())
                df = StatsBombDataLoader().ingest_custom_csv_or_json(str(tmp), match_id=999001)
                st.session_state["match_id"] = 999001
                st.session_state["upload_df"] = df
                st.session_state["chat_history"] = []
                st.rerun()
            except Exception as exc:
                st.warning(f"Não foi possível ler o arquivo: {exc}")


def render_selected_match_card(bundle, target_team_options, current_team: Optional[str]) -> str:
    """Cartão da partida aberta + seletor da equipe em foco. Retorna a equipe escolhida."""
    m = bundle.meta or {}
    st.sidebar.markdown("---")
    hs, as_ = m.get("home_score"), m.get("away_score")
    score = f"{hs} – {as_}" if hs is not None and as_ is not None else "x"
    st.sidebar.markdown(
        f"""<div class="til-match-card"><div class="teams">{m.get('home_team_name', '')} {score} {m.get('away_team_name', '')}</div>
        <div class="meta">{m.get('competition_name', '')} · {m.get('season_name', '')} · {m.get('match_date', '')}</div>
        <div class="meta">{BADGES.get(bundle.level, bundle.level)}</div></div>""",
        unsafe_allow_html=True,
    )
    if not target_team_options:
        return current_team or ""
    idx = target_team_options.index(current_team) if current_team in target_team_options else 0
    team = st.sidebar.selectbox("Equipe em foco", target_team_options, index=idx, key="team_focus_select")
    st.sidebar.caption(
        "Eventos reais: StatsBomb Open Data e Wyscout Public Dataset (CC BY 4.0). "
        "Boxscore: API-Football / ESPN. Placar: football-data.org."
    )
    return team
