"""
🔎 Busca única — uma caixa para tudo: partidas, times, jogadores e competições.
Clicar em qualquer resultado abre a tela dele (com "← Voltar"). Por padrão só entram jogos analisáveis
(eventos ou estatísticas); jogos só com placar ficam de fora (Bastidores › Dados para mostrar).
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from src.data_hub.registry import BADGES, DataLevel
from src.ui import nav
from src.ui.components import empty_state, hero, result_card_html
from src.ui.crests import crest_img
from src.ui.names import pt

LEVEL_ORDER = {DataLevel.EVENTS: 0, DataLevel.BOXSCORE: 1, DataLevel.UPLOAD: 2, DataLevel.SIMULATED: 3, DataLevel.RESULT: 4}


def one_per_game(out: pd.DataFrame) -> pd.DataFrame:
    """A mesma partida em várias bases vira um cartão só — o da versão mais rica (eventos > estatísticas > placar)."""
    from src.data_lake.ids import team_core

    if out is None or out.empty:
        return out
    out = out.drop_duplicates("match_id").assign(_lv=out["data_level"].map(LEVEL_ORDER).fillna(9))
    pair = [" x ".join(sorted((team_core(h), team_core(a)))) for h, a in zip(out["home_team_name"], out["away_team_name"])]
    out = out.assign(_k=[f"{str(d)[:10]}|{p}" for d, p in zip(out["match_date"], pair)])
    return out.sort_values("_lv").drop_duplicates("_k").drop(columns="_k")


@st.cache_data(show_spinner=False, max_entries=8)
def team_table(version: str, only: bool, real: bool = True) -> pd.DataFrame:
    """Uma linha por nome de time: nº de jogos analisáveis e o núcleo do nome (para agrupar variações)."""
    from src.data_lake.ids import team_core
    from src.ui.context import cached_catalog

    c = cached_catalog(include_score_only=not only)
    if c.empty:
        return pd.DataFrame(columns=["nome", "jogos", "core"])
    s = pd.concat([c["home_team_name"], c["away_team_name"]]).dropna().value_counts()
    t = pd.DataFrame({"nome": s.index, "jogos": s.values})
    t["core"] = t["nome"].map(team_core)
    return t


@st.cache_data(show_spinner=False, max_entries=8)
def competition_table(version: str, only: bool, real: bool = True) -> pd.DataFrame:
    from src.ui.context import cached_catalog

    c = cached_catalog(include_score_only=not only)
    if c.empty:
        return pd.DataFrame(columns=["competicao", "jogos", "temporadas", "pais"])
    g = c.groupby("competition_name")
    return pd.DataFrame({"jogos": g.size(), "temporadas": g["season_name"].nunique(),
                         "pais": g["country_name"].agg(lambda s: next((x for x in s if isinstance(x, str) and x), ""))}
                        ).reset_index().rename(columns={"competition_name": "competicao"})


def find_teams(q: str, version: str, only: bool, n: int = 8) -> pd.DataFrame:
    from src.data_hub.search import fast_scores

    from src.ui.context import only_real

    t = team_table(version, only, only_real())
    if t.empty or len(q.strip()) < 2:
        return t.iloc[0:0]
    sc = fast_scores(q, t["nome"].tolist())
    t = t.assign(score=t["nome"].map(sc))
    t = t[t["score"] >= 0.86]
    # agrupa variações do mesmo time ("Man United" / "Manchester United FC") somando os jogos
    g = t.sort_values("jogos", ascending=False).groupby("core").agg(nome=("nome", "first"), jogos=("jogos", "sum"),
                                                                    score=("score", "max")).reset_index()
    return g.sort_values(["score", "jogos"], ascending=False).head(n)


def find_competitions(q: str, version: str, only: bool, n: int = 6) -> pd.DataFrame:
    from src.data_lake.ids import norm

    from src.ui.context import only_real

    c = competition_table(version, only, only_real())
    if c.empty or len(q.strip()) < 3:
        return c.iloc[0:0]
    nq = norm(q)
    hit = c[c["competicao"].map(lambda x: nq in norm(x))]
    return hit.sort_values("jogos", ascending=False).head(n)


def find_players(q: str, version: str, n: int = 8) -> pd.DataFrame:
    if len(q.strip()) < 3:
        return pd.DataFrame()
    from src.ui.pages.players_search import _norm, player_index

    idx = player_index(version)
    if idx.empty:
        return idx
    core = _norm(q)
    hit = idx[idx["core"].str.contains(core, regex=False) | idx["nome"].str.lower().str.contains(q.strip().lower(), regex=False)]
    if hit.empty:
        return hit
    g = hit.groupby("core").agg(nome=("nome", lambda s: min(s, key=len)),
                                clube=("clube", lambda s: next((x for x in s if isinstance(x, str) and x), "")),
                                fontes=("fonte", lambda s: ", ".join(sorted(set(s)))),
                                jogos=("jogos", "sum")).reset_index()
    return g.sort_values("jogos", ascending=False).head(n)


def find_matches(q: str) -> pd.DataFrame:
    """Partidas: confronto ("A x B", com ou sem ano) pelo buscador; nome solto de time não lista jogos aqui."""
    from src.ui.context import get_service

    try:
        res = get_service().finder.find(q, allow_remote=False)
    except Exception:
        return pd.DataFrame()
    out = res["candidates"] if not res["candidates"].empty else res.get("suggestions", pd.DataFrame())
    if out is None or out.empty:
        return pd.DataFrame()
    q_teams = getattr(res.get("query"), "teams", []) or []
    if len(q_teams) < 2 and not getattr(res.get("query"), "year", None):
        return pd.DataFrame()                       # só um time: o resultado certo é a tela do time
    return one_per_game(out).sort_values(["match_date", "_lv"], ascending=[False, True])


def _n(v) -> str:
    v = int(v)
    return f"{v} jogo" if v == 1 else f"{v} jogos"


def match_cards(df: pd.DataFrame, key: str, limit: int = 25) -> None:
    for i, m in enumerate(df.head(limit).to_dict("records")):
        a, b = st.columns([8, 1.3])
        a.markdown(result_card_html(m, BADGES.get(m.get("data_level"), m.get("data_level", ""))), unsafe_allow_html=True)
        b.write("")
        if b.button("Analisar →", key=f"{key}_{m['match_id']}_{i}", use_container_width=True, type="primary"):
            nav.open_view("jogo", match_id=int(m["match_id"]))


def render(_ctx=None) -> None:
    from src.ui.context import analyzable_only, get_service

    q = (st.session_state.get("global_q") or nav.param("q") or st.session_state.get("_last_q") or "").strip()
    if not q:
        hero("Buscar", "Um jogo, um time, um jogador ou uma competição",
             "Digite na caixa do topo. Clique no resultado para abrir a análise. Só aparecem jogos com dados "
             "para analisar (todos os lances ✅ ou estatísticas 📊).")
        _showcase()
        return
    version, only = get_service().db.catalog_version(), analyzable_only()
    with st.spinner("Procurando..."):
        matches = find_matches(q)
        teams = find_teams(q, version, only)
        players = find_players(q, version)
        comps = find_competitions(q, version, only)
    st.markdown(f"#### Resultados para “{q}”")
    if matches.empty and teams.empty and players.empty and comps.empty:
        empty_state("Nada encontrado com dados para analisar", "Confira a grafia, tente só o nome do time ou do jogador.",
                    "🔎", "Jogos só com placar ficam fora da busca (Bastidores › Dados para incluí-los).")
        return
    if not matches.empty:
        st.markdown(f"##### 🏟️ Partidas · {len(matches)}")
        match_cards(matches, "srch_m")
    left, mid, right = st.columns(3)
    with left:
        st.markdown("##### 🛡️ Times")
        if teams.empty:
            st.caption("Nenhum time com esse nome.")
        for i, r in enumerate(teams.to_dict("records")):
            c1, c2 = st.columns([1, 6])
            c1.markdown(crest_img(r["nome"]), unsafe_allow_html=True)
            with c2:
                nav.link(f"{pt(r['nome'])} · {_n(r['jogos'])}", "time", key=f"srch_t_{i}", name=r["nome"])
    with mid:
        st.markdown("##### 👤 Jogadores")
        if players.empty:
            st.caption("Nenhum jogador com esse nome.")
        for i, r in enumerate(players.to_dict("records")):
            extra = f" · {r['clube']}" if r.get("clube") else ""
            nav.link(f"{r['nome']}{extra}", "jogador", key=f"srch_p_{i}", name=r["nome"], core=r["core"])
    with right:
        st.markdown("##### 🏆 Competições")
        if comps.empty:
            st.caption("Nenhuma competição com esse nome.")
        for i, r in enumerate(comps.to_dict("records")):
            nav.link(f"{r['competicao']} · {_n(r['jogos'])}", "competicao", key=f"srch_c_{i}", name=r["competicao"])


def _showcase() -> None:
    """Sem busca: atalhos para jogos com todos os lances (os mais completos da base)."""
    from src.ui.context import cached_catalog

    cat = cached_catalog("data_level = 'EVENTS'")
    if cat.empty:
        return
    st.markdown("##### ✅ Jogos com todos os lances (análise completa)")
    match_cards(cat.sort_values("match_date", ascending=False), "show", limit=12)
