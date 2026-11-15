"""🛡️ Tela do time — perfil, campanha, TODOS os jogos com dados (paginados), elenco e xG. Aberta pela busca única."""

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


def same_team_names(name: str) -> List[str]:
    """Variações do mesmo time entre as fontes ('Man United', 'Manchester United', 'Manchester United FC')."""
    from src.data_hub.search import fast_scores
    from src.data_lake.ids import team_core
    from src.ui.context import get_service
    from src.ui.pages.search_all import team_table

    t = team_table(get_service().db.stable_version(), False)
    if t.empty:
        return [name]
    core = team_core(name)
    same = set(t.loc[t["core"] == core, "nome"])
    sc = fast_scores(name, t["nome"].tolist())
    same |= {n for n, v in sc.items() if v >= 0.92}
    # time feminino, sub-20, reservas etc. não são "o mesmo time" (Barcelona × Barcelona WFC)
    import re as _re

    tag = _re.compile(r"\b(wfc|women|womens|ladies|feminino|femenino|f[eé]minin|fem|w|u-?\d{2}|sub-?\d{2}|ii|b|reserves?)\b|\(w\)",
                      _re.I)
    if not tag.search(name):
        same = {n for n in same if not tag.search(n)}
    return sorted(same | {name})


def team_matches(name, include_score_only: bool = False) -> pd.DataFrame:
    """Jogos do time (uma linha por partida, versão mais rica). `name` pode ser um nome ou a lista de variações."""
    from src.ui.context import cached_catalog
    from src.ui.pages.search_all import one_per_game

    names = [name] if isinstance(name, str) else list(name)
    c = cached_catalog(include_score_only=include_score_only)
    m = c[c["home_team_name"].isin(names) | c["away_team_name"].isin(names)]
    m = m[m["home_score"].notna() & m["away_score"].notna()]
    if m.empty:
        return m
    return one_per_game(m).sort_values("match_date", ascending=False)


def record(name, m: pd.DataFrame) -> dict:
    if m.empty:
        return {}
    names = [name] if isinstance(name, str) else list(name)
    home = m["home_team_name"].isin(names)
    gf = (m["home_score"].where(home, m["away_score"])).astype(float)
    ga = (m["away_score"].where(home, m["home_score"])).astype(float)
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


PAGE = 25


def upcoming(names) -> pd.DataFrame:
    """Próximos jogos do time (lake 'agenda', alimentado pelo open-matchday)."""
    try:
        from datetime import date

        from src.data_hub.service import _same
        from src.data_lake.ids import team_core
        from src.data_lake.lake import Lake

        lake = Lake(sqlite_path=None)
        if not lake.exists("agenda"):
            return pd.DataFrame()
        ag = lake.read("agenda")
        cores = {team_core(n) for n in names}
        hit = ag[[any(_same(team_core(h), c) or _same(team_core(a), c) for c in cores)
                  for h, a in zip(ag["mandante"], ag["visitante"])]]
        hit = hit[hit["data"].astype(str) >= date.today().isoformat()].sort_values(["data", "hora"])
        return hit[["data", "hora", "mandante", "visitante", "competicao"]].rename(columns={"competicao": "competição"})
    except Exception:
        return pd.DataFrame()


def render(_ctx=None) -> None:
    from src.ui import nav
    from src.ui.names import pt

    nav.back_button(key="team_back")
    name = nav.param("name")
    if not name:
        empty_state("Nenhum time escolhido", "Use a busca no topo e clique no time.", "🛡️")
        return
    names = same_team_names(name)
    m = team_matches(names)                                    # jogos com dados para análise
    allm = team_matches(names, include_score_only=True)        # campanha usa todos os resultados
    r = record(names, allm)
    lake, key, ids = _lake_team(name)
    fontes = sorted(ids["fonte"].unique()) if not ids.empty else sorted(m["data_source"].unique()) if not m.empty else []
    st.markdown(f'<div class="til-profile">{crest_img(name, "lg")}<div><div class="n">{pt(name)}</div>'
                f'<div class="d">{len(m)} jogos com dados para análise · {len(allm)} resultados no total'
                + (f" · fontes: {', '.join(fontes)}" if fontes else "") + f'</div>{form_html(r.get("forma", []))}</div></div>',
                unsafe_allow_html=True)
    k = st.columns(5)
    k[0].metric("Jogos (todos)", r.get("jogos", 0))
    k[1].metric("V / E / D", f"{r.get('V', 0)} / {r.get('E', 0)} / {r.get('D', 0)}")
    k[2].metric("Gols pró / contra", f"{r.get('gp', 0)} / {r.get('gc', 0)}")
    k[3].metric("Aproveitamento", f"{r.get('aprov', 0)}%")
    k[4].metric("Com todos os lances (✅)", int((m["data_level"] == "EVENTS").sum()) if not m.empty else 0)

    nxt = upcoming(names)
    if not nxt.empty:
        st.markdown("##### 📅 Próximos jogos")
        st.caption("Agenda do open-matchday (horário de início em CET-1, como a fonte publica).")
        comparison_table(nxt.head(5))
    t1, t2, t3 = st.tabs(["🗓️ Jogos", "💶 Elenco e valores", "📈 Temporada (xG)"])
    with t1:
        if m.empty:
            empty_state("Nenhum jogo deste time com estatísticas ou lances", "Só existem resultados (placar) dele nas "
                        "fontes abertas.", "🗓️", "Bastidores › Dados: ligue 'mostrar jogos só com placar' para vê-los.")
        else:
            f1, f2 = st.columns(2)
            seasons = ["todas"] + sorted(m["season_name"].dropna().astype(str).unique(), reverse=True)
            sea = f1.selectbox("Temporada", seasons, key=f"team_season_{name}")
            comps = ["todas"] + m["competition_name"].dropna().value_counts().index.tolist()
            cmp_ = f2.selectbox("Competição", comps, key=f"team_comp_{name}")
            mm = m if sea == "todas" else m[m["season_name"].astype(str) == sea]
            mm = mm if cmp_ == "todas" else mm[mm["competition_name"] == cmp_]
            if cmp_ != "todas":
                nav.link(f"🏆 Abrir {cmp_}", "competicao", key=f"team_open_comp_{name}", name=cmp_,
                         season=None if sea == "todas" else sea)
            pk = f"team_page_{name}_{sea}_{cmp_}"
            shown = int(st.session_state.get(pk, PAGE))
            st.caption(f"{len(mm)} jogo(s) · mostrando {min(shown, len(mm))}")
            for i, row in enumerate(mm.head(shown).to_dict("records")):
                a, b = st.columns([8, 1.3])
                a.markdown(result_card_html(row, BADGES.get(row["data_level"], row["data_level"])), unsafe_allow_html=True)
                b.write("")
                if b.button("Analisar →", key=f"team_open_{row['match_id']}_{i}", use_container_width=True, type="primary"):
                    st.session_state["team_focus"] = next((n for n in names if n in (row["home_team_name"],
                                                                                      row["away_team_name"])), None)
                    nav.open_view("jogo", match_id=int(row["match_id"]))
            if shown < len(mm) and st.button(f"Mostrar mais {min(PAGE, len(mm) - shown)}", key=f"more_{pk}",
                                             use_container_width=True):
                st.session_state[pk] = shown + PAGE
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
