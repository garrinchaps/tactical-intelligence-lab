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
    # rodada 7: o mesmo jogo aparecia 2–3 vezes ("só placar", "estatísticas", "lances") quando as fontes gravam a data
    # com 1 dia de diferença (UTC × horário local) ou escrevem o time diferente (Brazil × Brasil, Atlético-MG ×
    # Atlético Mineiro). Agora: data ±1 dia + nome traduzido/núcleo + nomes parecidos; fica a versão mais rica.
    canon = _team_canon()
    keys = [tuple(sorted((canon(h), canon(a)))) for h, a in zip(out["home_team_name"], out["away_team_name"])]
    days = pd.to_datetime(out["match_date"].astype(str).str[:10], errors="coerce")
    out = out.assign(_t1=[k[0] for k in keys], _t2=[k[1] for k in keys], _day=days).sort_values(["_day", "_lv"])
    from src.data_hub.service import _same

    rows = out.to_dict("records")
    group = [-1] * len(rows)
    gid = 0
    for i, r in enumerate(rows):
        if group[i] >= 0:
            continue
        group[i] = gid
        for j in range(i + 1, len(rows)):
            s = rows[j]
            if pd.isna(r["_day"]) or pd.isna(s["_day"]) or (s["_day"] - r["_day"]).days > 1:
                break                                      # ordenado por data: depois disso não há mais candidatos
            if group[j] >= 0:
                continue
            same = (r["_t1"] == s["_t1"] and r["_t2"] == s["_t2"]) or (
                _same(r["_t1"], s["_t1"]) and _same(r["_t2"], s["_t2"])) or (
                _same(r["_t1"], s["_t2"]) and _same(r["_t2"], s["_t1"]))
            if same:
                group[j] = gid
        gid += 1
    out = out.assign(_g=group).sort_values(["_g", "_lv"])
    return out.drop_duplicates("_g").drop(columns=["_t1", "_t2", "_day", "_g"])


def _team_canon():
    """Núcleo do nome + seleções em português traduzidas (Brasil → brazil), para casar as fontes."""
    from src.data_hub.search import TEAM_ALIASES, norm
    from src.data_lake.ids import team_core

    tr = {}
    for pt, ens in TEAM_ALIASES.items():
        target = team_core(ens[0])
        tr[team_core(pt)] = target
        for e in ens:
            tr[team_core(e)] = target
    return lambda name: (lambda c: tr.get(c, c))(team_core(name))


@st.cache_data(show_spinner=False, max_entries=8)
def team_table(version: str, only, real: bool = True) -> pd.DataFrame:
    """Uma linha por nome de time: nº de jogos analisáveis e o núcleo do nome (para agrupar variações)."""
    from src.data_lake.ids import team_core
    from src.ui.context import cached_catalog

    c = cached_catalog() if isinstance(only, str) else cached_catalog(include_score_only=not only)
    if c.empty:
        return pd.DataFrame(columns=["nome", "jogos", "core"])
    s = pd.concat([c["home_team_name"], c["away_team_name"]]).dropna().value_counts()
    t = pd.DataFrame({"nome": s.index, "jogos": s.values})
    t["core"] = t["nome"].map(team_core)
    return t


@st.cache_data(show_spinner=False, max_entries=8)
def competition_table(version: str, only, real: bool = True) -> pd.DataFrame:
    from src.ui.context import cached_catalog

    c = cached_catalog() if isinstance(only, str) else cached_catalog(include_score_only=not only)
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
    hit = idx[idx["pessoa"].isin(set(hit["pessoa"]))] if "pessoa" in idx else hit   # todas as grafias da pessoa
    g = hit.groupby(hit["pessoa"] if "pessoa" in hit else hit["core"]).agg(
                                nome=("nome", lambda s: min(s, key=len)),
                                clube=("clube", lambda s: next((x for x in s if isinstance(x, str) and x), "")),
                                fontes=("fonte", lambda s: ", ".join(sorted(set(s)))),
                                jogos=("jogos", "sum")).reset_index()
    g = g.rename(columns={g.columns[0]: "core"})
    tm = hit[hit["fonte"] == "Transfermarkt"].dropna(subset=["clube"])
    if not tm.empty and "pessoa" in tm:                # clube atual = o do Transfermarkt (seleção/histórico ficam atrás)
        cur = tm.groupby("pessoa")["clube"].first()
        g["clube"] = [cur.get(c, cl) for c, cl in zip(g["core"], g["clube"])]
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
             "Digite na caixa do topo. Clique no resultado para abrir a análise. Escolha ao lado da busca que "
             "jogos aparecem: 🟢 com todos os lances, 📊 com estatísticas, 📄 só placar — ou os três.")
        _showcase()
        return
    from src.ui.context import chosen_levels

    version, only = get_service().db.stable_version(), "|".join(chosen_levels())   # níveis escolhidos no topo
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
