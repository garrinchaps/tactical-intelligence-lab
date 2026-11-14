"""🛡️ Clubes — pesquisa de clubes e seleções: perfil, forma recente, números da temporada, elenco e jogos."""

from __future__ import annotations

from typing import List

import pandas as pd
import streamlit as st

from src.data_hub.registry import BADGES
from src.ui.components import comparison_table, empty_state, form_html, hero, result_card_html
from src.ui.crests import crest_img


@st.cache_data(show_spinner=False, ttl=900)
def _team_names(version: str) -> List[str]:
    from src.ui.context import cached_catalog

    c = cached_catalog()
    return sorted(pd.unique(pd.concat([c["home_team_name"], c["away_team_name"]]).dropna()))


def team_matches(name: str) -> pd.DataFrame:
    from src.ui.context import cached_catalog

    c = cached_catalog()
    m = c[(c["home_team_name"] == name) | (c["away_team_name"] == name)]
    m = m[m["home_score"].notna() & m["away_score"].notna()]
    return m.sort_values("match_date", ascending=False).drop_duplicates(["match_date", "home_team_name", "away_team_name"])


def record(name: str, m: pd.DataFrame) -> dict:
    if m.empty:
        return {}
    gf = (m["home_score"].where(m["home_team_name"] == name, m["away_score"])).astype(float)
    ga = (m["away_score"].where(m["home_team_name"] == name, m["home_score"])).astype(float)
    res = ["V" if f > a else ("E" if f == a else "D") for f, a in zip(gf, ga)]
    return {"jogos": len(m), "V": res.count("V"), "E": res.count("E"), "D": res.count("D"), "gp": int(gf.sum()), "gc": int(ga.sum()),
            "forma": list(reversed(res[:5])), "aprov": round(100 * (3 * res.count("V") + res.count("E")) / (3 * len(res)), 1)}


def _lake_team(name: str):
    try:
        from src.data_lake.ids import team_core
        from src.data_lake.lake import Lake

        lake = Lake(sqlite_path=None)
        if not lake.exists("team_ids"):
            return lake, None, pd.DataFrame()
        ids = lake.read("team_ids")
        hit = ids[ids["nome"] == name]
        if hit.empty:
            hit = ids[ids["nome"].map(team_core) == team_core(name)]
        key = hit["team_key"].iloc[0] if not hit.empty else None
        return lake, key, ids[ids["team_key"] == key] if key else pd.DataFrame()
    except Exception:
        return None, None, pd.DataFrame()


def render(_ctx=None) -> None:
    from src.ui.context import filter_by_team, get_service

    hero("Clubes", "Pesquise clubes e seleções", "Forma recente, números da temporada, valor do elenco e todos os jogos "
         "disponíveis em todas as fontes.")
    q = st.text_input("Clube ou seleção", key="club_q", placeholder="ex.: Flamengo, Bayer Leverkusen, Argentina, Liverpool")
    if not q.strip():
        empty_state("Digite o nome de um clube ou seleção", icon="🛡️")
        return
    names = _team_names(get_service().db.catalog_version())
    cand = filter_by_team(pd.DataFrame({"home_team_name": names, "away_team_name": names}), q, 0.86)["home_team_name"].tolist()
    if not cand:
        empty_state("Clube não encontrado no catálogo", "Confira a grafia ou sincronize mais fontes.", "🔎")
        return
    counts = {n: len(team_matches(n)) for n in cand[:30]}
    cand = sorted(counts, key=lambda n: -counts[n])
    name = st.selectbox("Resultado", cand, format_func=lambda n: f"{n} · {counts[n]} jogos") if len(cand) > 1 else cand[0]
    m = team_matches(name)
    r = record(name, m)
    lake, key, ids = _lake_team(name)
    fontes = sorted(ids["fonte"].unique()) if not ids.empty else sorted(m["data_source"].unique())
    st.markdown(f'<div class="til-profile">{crest_img(name, "lg")}<div><div class="n">{name}</div>'
                f'<div class="d">{len(m)} jogos com placar · fontes: {", ".join(fontes)}</div>'
                f'{form_html(r.get("forma", []))}</div></div>', unsafe_allow_html=True)
    k = st.columns(5)
    k[0].metric("Jogos", r.get("jogos", 0))
    k[1].metric("V / E / D", f"{r.get('V', 0)} / {r.get('E', 0)} / {r.get('D', 0)}")
    k[2].metric("Gols pró / contra", f"{r.get('gp', 0)} / {r.get('gc', 0)}")
    k[3].metric("Aproveitamento", f"{r.get('aprov', 0)}%")
    k[4].metric("Com eventos (✅)", int((m["data_level"] == "EVENTS").sum()) if not m.empty else 0)
    st.caption("Todos os jogos com placar do catálogo (todas as competições e fontes, sem duplicar o mesmo jogo).")

    t1, t2, t3 = st.tabs(["🗓️ Jogos", "💶 Elenco e valores", "📈 Temporada (xG)"])
    with t1:
        seasons = ["todas"] + sorted(m["season_name"].dropna().astype(str).unique(), reverse=True)
        sea = st.selectbox("Temporada", seasons, key="club_season")
        mm = m if sea == "todas" else m[m["season_name"].astype(str) == sea]
        for i, row in enumerate(mm.head(30).to_dict("records")):
            a, b = st.columns([8, 1.2])
            a.markdown(result_card_html(row, BADGES.get(row["data_level"], row["data_level"])), unsafe_allow_html=True)
            if b.button("Abrir", key=f"club_open_{row['match_id']}_{i}", use_container_width=True):
                st.session_state["match_id"] = int(row["match_id"])
                st.session_state["team_focus"] = name
                st.session_state["games_section"] = "📊 Resumo"
                st.session_state["goto"] = "jogos"
                st.rerun()
    with t2:
        if lake is None or ids.empty or not lake.exists("tm_clubes"):
            empty_state("Sem dados do Transfermarkt para este clube", "", "💶",
                        "python -m src.data_hub.sync --only transfermarkt lake")
        else:
            tm_id = ids[ids["fonte"] == "transfermarkt"]["id_fonte"].astype(str).tolist()
            clubs = lake.read("tm_clubes")
            cl = clubs[clubs["transfermarkt_id"].astype(str).isin(tm_id)]
            if not cl.empty:
                c = cl.iloc[0]
                x = st.columns(4)
                x[0].metric("Elenco", int(c.get("elenco", 0) or 0))
                x[1].metric("Idade média", c.get("idade_media", "—"))
                x[2].metric("Estádio", str(c.get("estadio", "—"))[:22])
                x[3].metric("Capacidade", f"{int(c.get('capacidade', 0) or 0):,}".replace(",", "."))
            pl = lake.read("tm_jogadores") if lake.exists("tm_jogadores") else pd.DataFrame()
            if not pl.empty:
                sq = pl[pl["clube_id"].astype(str).isin(tm_id)].sort_values("valor_mercado_eur", ascending=False)
                if not sq.empty:
                    st.metric("Valor somado do elenco (€ mi)", round(sq["valor_mercado_eur"].fillna(0).sum() / 1e6, 1))
                    comparison_table(sq[["nome", "posicao", "funcao", "nascimento", "nacionalidade", "valor_mercado_eur"]]
                                     .assign(valor_mercado_eur=lambda d: (d["valor_mercado_eur"] / 1e6).round(1))
                                     .rename(columns={"valor_mercado_eur": "valor (€ mi)"}).head(40),
                                     "Fonte: Transfermarkt (transfermarkt-datasets).")
    with t3:
        if lake is None or ids.empty or not lake.exists("us_partidas"):
            empty_state("Sem xG do Understat para este clube", "O Understat cobre as 5 grandes ligas europeias e a Rússia.", "📈")
        else:
            us_names = ids[ids["fonte"] == "understat"]["nome"].tolist()
            u = lake.read("us_partidas")
            u = u[u["mandante"].isin(us_names) | u["visitante"].isin(us_names)].copy()
            if u.empty:
                empty_state("Sem partidas no Understat", icon="📈")
            else:
                home = u["mandante"].isin(us_names)
                u["xg_pro"] = u["xg_mandante"].where(home, u["xg_visitante"])
                u["xg_contra"] = u["xg_visitante"].where(home, u["xg_mandante"])
                u["adversario"] = u["visitante"].where(home, u["mandante"])
                by = u.groupby("temporada")[["xg_pro", "xg_contra"]].mean().round(2).reset_index()
                comparison_table(by.rename(columns={"xg_pro": "xG pró por jogo", "xg_contra": "xG contra por jogo"}),
                                 "Fonte: Understat.")
                from src.ui import charts

                last = u.sort_values("data").tail(20)
                st.plotly_chart(charts.lines(last.assign(jogo=last["data"] + " " + last["adversario"]), "jogo",
                                             ["xg_pro", "xg_contra"], f"xG por jogo — últimos {len(last)}", "xG"),
                                use_container_width=True)
