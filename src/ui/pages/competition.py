"""🏆 Tela da competição — temporadas, classificação (calculada dos resultados) e todos os jogos com dados."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.data_hub.registry import BADGES
from src.ui import nav
from src.ui.components import comparison_table, empty_state, result_card_html
from src.ui.names import pt

PAGE = 25


def standings(m: pd.DataFrame) -> pd.DataFrame:
    """Tabela de pontos (3/1/0) a partir dos placares; uma linha por partida já deduplicada."""
    rows = []
    for r in m.dropna(subset=["home_score", "away_score"]).itertuples():
        hs, as_ = int(r.home_score), int(r.away_score)
        for team, gf, ga in ((r.home_team_name, hs, as_), (r.away_team_name, as_, hs)):
            rows.append({"time": team, "J": 1, "V": int(gf > ga), "E": int(gf == ga), "D": int(gf < ga), "GP": gf, "GC": ga})
    if not rows:
        return pd.DataFrame(columns=["time", "P", "J", "V", "E", "D", "GP", "GC", "SG"])
    t = pd.DataFrame(rows).groupby("time").sum().reset_index()
    t["SG"] = t["GP"] - t["GC"]
    t["P"] = 3 * t["V"] + t["E"]
    t = t.sort_values(["P", "SG", "GP"], ascending=False).reset_index(drop=True)
    t.insert(0, "#", range(1, len(t) + 1))
    return t[["#", "time", "P", "J", "V", "E", "D", "GP", "GC", "SG"]]


def render(_ctx=None) -> None:
    from src.ui.context import cached_catalog
    from src.ui.pages.search_all import one_per_game

    nav.back_button(key="comp_back")
    name = nav.param("name")
    if not name:
        empty_state("Nenhuma competição escolhida", "Use a busca no topo e clique na competição.", "🏆")
        return
    allm = cached_catalog("competition_name = ?", (name,), include_score_only=True)
    if allm.empty:
        empty_state("Competição sem jogos na base", icon="🏆")
        return
    seasons = sorted(allm["season_name"].dropna().astype(str).unique(), reverse=True)
    want = nav.param("season")
    st.markdown(f"## 🏆 {name}")
    sea = st.selectbox("Temporada", seasons, index=seasons.index(want) if want in seasons else 0, key=f"comp_season_{name}")
    allm = one_per_game(allm[allm["season_name"].astype(str) == sea])
    rich = allm[allm["data_level"].isin(["EVENTS", "BOXSCORE"])]
    k = st.columns(4)
    k[0].metric("Jogos na temporada", len(allm))
    k[1].metric("Com todos os lances (✅)", int((allm["data_level"] == "EVENTS").sum()))
    k[2].metric("Com estatísticas (📊)", int((allm["data_level"] == "BOXSCORE").sum()))
    k[3].metric("Times", len(set(allm["home_team_name"]) | set(allm["away_team_name"])))
    t1, t2 = st.tabs(["🗓️ Jogos com dados", "📋 Classificação"])
    with t1:
        if rich.empty:
            empty_state("Nesta temporada só há placares", "Nenhuma fonte aberta traz estatísticas ou lances destes jogos.", "🗓️")
        else:
            pk = f"comp_page_{name}_{sea}"
            shown = int(st.session_state.get(pk, PAGE))
            rich = rich.sort_values("match_date", ascending=False)
            st.caption(f"{len(rich)} jogo(s) com dados · mostrando {min(shown, len(rich))}")
            for i, row in enumerate(rich.head(shown).to_dict("records")):
                a, b = st.columns([8, 1.3])
                a.markdown(result_card_html(row, BADGES.get(row["data_level"], row["data_level"])), unsafe_allow_html=True)
                b.write("")
                if b.button("Analisar →", key=f"comp_open_{row['match_id']}_{i}", use_container_width=True, type="primary"):
                    nav.open_view("jogo", match_id=int(row["match_id"]))
            if shown < len(rich) and st.button(f"Mostrar mais {min(PAGE, len(rich) - shown)}", key=f"more_{pk}",
                                               use_container_width=True):
                st.session_state[pk] = shown + PAGE
                st.rerun()
    with t2:
        tab = standings(allm)
        if tab.empty:
            empty_state("Sem placares para montar a tabela", icon="📋")
        else:
            st.caption("Calculada a partir dos placares da base (3 pontos por vitória). Em copas e fases de grupo, "
                       "é só um resumo de desempenho, não a tabela oficial.")
            comparison_table(tab.assign(time=tab["time"].map(pt)))
            pick = st.selectbox("Abrir o time", tab["time"].tolist(), format_func=pt, key=f"comp_team_{name}_{sea}")
            nav.link(f"🛡️ Ver {pt(pick)}", "time", key=f"comp_team_open_{name}", name=pick)
