"""
🔎 Busca única — uma caixa para tudo: partidas, times, jogadores e competições.
Clicar em qualquer resultado abre a tela dele (com "← Voltar"). Por padrão só entram jogos analisáveis
(eventos ou estatísticas); jogos só com placar ficam de fora (Bastidores › Dados para mostrar).
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from src.ui.perf import timed as _perf_timed

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
    out = out.assign(_t1=[k[0] for k in keys], _t2=[k[1] for k in keys], _day=days,
                     _h=[canon(h) for h in out["home_team_name"]], _a=[canon(a) for a in out["away_team_name"]]
                     ).sort_values(["_day", "_lv"])
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
            if not same:
                # rodada 11: um time igual + MESMO placar (na mesma ordem) em ±1 dia = a mesma partida, mesmo que a outra
                # fonte escreva o adversário de outro jeito ("Racing Santander" × "R. Racing Club", "LDU" × "Liga de Quito")
                one = {r["_h"], r["_a"]} & {s["_h"], s["_a"]}
                same = bool(one) and _score(r) is not None and _score(r) == _score(s) and (
                    (r["_h"] == s["_h"]) or (r["_a"] == s["_a"]))
            if same:
                group[j] = gid
        gid += 1
    out = out.assign(_g=group).sort_values(["_g", "_lv"])
    return out.drop_duplicates("_g").drop(columns=["_t1", "_t2", "_day", "_g", "_h", "_a"])


_WARMED: set = set()


def _prewarm_teams(names: tuple) -> None:
    """Calcula em segundo plano (thread) o estilo/histórico dos times encontrados, para a página do time abrir na hora
    quando o usuário clicar. Usa os mesmos caches da página (em disco); se algo falhar, a página calcula normalmente."""
    import threading

    todo = [n for n in names if n not in _WARMED]
    if not todo:
        return
    _WARMED.update(todo)

    def run():
        try:
            from src.ui.context import get_service
            from src.ui.pages import clubs as C

            from src.ui.busy import yield_to_user

            db = get_service().db
            for n in todo:
                yield_to_user()                       # rodada 27f: não disputa o processador com a página aberta
                ns = C.same_team_names(n)
                C.team_matches(ns)
                yield_to_user()
                C._style_data(tuple(ns), db.team_version(ns))
                yield_to_user()
                C._formation_data(tuple(ns), db.team_version(ns))
        except Exception:
            pass

    threading.Thread(target=run, name="til-prewarm", daemon=True).start()


def _score(r):
    try:
        return (int(r["home_score"]), int(r["away_score"]))
    except (TypeError, ValueError, KeyError):
        return None


def _team_canon():
    """Núcleo do nome + seleções em português traduzidas (Brasil → brazil), para casar as fontes."""
    from src.data_hub.search import TEAM_ALIASES, norm
    from src.data_lake.ids import team_core

    tr = {}
    for pt, ens in TEAM_ALIASES.items():
        cores = {team_core(e) for e in ens}
        # rodada 23: apelido AMBÍGUO ("tricolor" = Fluminense OU São Paulo) não pode traduzir nome nenhum — antes
        # "São Paulo" virava "fluminense" e jogos dos dois times se juntavam na busca e na tabela
        if len(cores) != 1:
            continue
        target = cores.pop()
        tr.setdefault(team_core(pt), target)
        for e in ens:
            tr.setdefault(team_core(e), target)
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
    if "country_name" in c:               # rodada 25: país mais comum dos jogos (separa Barcelona × Barcelona SC)
        both = pd.concat([c[["home_team_name", "country_name"]].set_axis(["nome", "pais"], axis=1),
                          c[["away_team_name", "country_name"]].set_axis(["nome", "pais"], axis=1)])
        both = both[both["pais"].fillna("").astype(str).str.len() > 0]
        if not both.empty:
            mode = both.groupby(["nome", "pais"]).size().reset_index(name="n").sort_values("n").drop_duplicates("nome", keep="last")
            t["pais"] = t["nome"].map(dict(zip(mode["nome"], mode["pais"]))).fillna("")
    if "pais" not in t:
        t["pais"] = ""
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


def team_core_(n):
    from src.data_lake.ids import team_core

    return team_core(n)


def find_teams(q: str, version: str, only: bool, n: int = 8) -> pd.DataFrame:
    from src.data_hub.search import fast_scores

    from src.ui.context import only_real

    t = team_table(version, only, only_real())
    if t.empty or len(q.strip()) < 2:
        return t.iloc[0:0]
    sc = fast_scores(q, t["nome"].tolist())
    t = t.assign(score=t["nome"].map(sc))
    t = t[t["score"] >= 0.86]
    # rodada 25: feminino/base e nomes sem palavra parecida saem; grafias do mesmo clube (núcleo + país) viram uma
    from src.ui.pages.squad import clean_team_options

    keep = set(clean_team_options(q, t.sort_values("score", ascending=False)["nome"].tolist(),
                                  dict(zip(t["nome"], t["jogos"])), dict(zip(t["nome"], t.get("pais", "")))))
    t = t[t["nome"].isin(keep) | t["core"].isin({team_core_(n) for n in keep})] if keep else t.iloc[0:0]
    pais = t.get("pais", pd.Series("", index=t.index)).fillna("").astype(str)
    known = t.assign(_p=pais)[pais != ""].sort_values("jogos").drop_duplicates("core", keep="last")
    pais = pais.where(pais != "", t["core"].map(dict(zip(known["core"], known["_p"]))).fillna(""))   # fonte sem país
    t = t.assign(_key=t["core"] + "|" + pais)
    # agrupa variações do mesmo time ("Man United" / "Manchester United FC") somando os jogos
    g = t.sort_values("jogos", ascending=False).groupby("_key").agg(nome=("nome", "first"), jogos=("jogos", "sum"),
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


@_perf_timed("search_all._search_all")
@st.cache_data(show_spinner=False, max_entries=64, ttl=3600)
def _search_all(q: str, version: str, only: str, real: bool):
    return find_matches(q), find_teams(q, version, only), find_players(q, version), find_competitions(q, version, only)


def _n(v) -> str:
    v = int(v)
    return f"{v} jogo" if v == 1 else f"{v} jogos"


def match_cards(df: pd.DataFrame, key: str, limit: int = 25) -> None:
    for i, m in enumerate(df.head(limit).to_dict("records")):
        a, b = st.columns([8, 1.3])
        a.markdown(result_card_html(m, BADGES.get(m.get("data_level"), m.get("data_level", ""))), unsafe_allow_html=True)
        b.write("")
        if b.button("Analisar →", key=f"{key}_{m['match_id']}_{i}", width="stretch", type="primary"):
            nav.open_view("jogo", match_id=int(m["match_id"]))


def search_box() -> str:
    """Rodada 20: a busca e o nível de dado ficam SÓ aqui (saíram do topo de todas as telas). Só busca no Enter/Buscar."""
    from src.ui.context import DEFAULT_LEVELS, LEVEL_CHOICES
    from src.ui.i18n import t

    inv = {v: k for k, v in LEVEL_CHOICES.items()}
    st.session_state.setdefault("w_levels", [inv[l] for l in (st.session_state.get("_levels") or DEFAULT_LEVELS)])
    pq = str(nav.param("q") or "").strip()
    if pq and pq != st.session_state.get("_q_seen"):     # busca pedida por outra tela (ex.: clique num nome)
        st.session_state["_q_seen"] = pq
        st.session_state["_last_q"] = pq
        st.session_state["global_q"] = pq
    if "global_q" not in st.session_state:
        st.session_state["global_q"] = st.session_state.get("_last_q", "")
    with st.form("til_search_form", border=False):
        a, b, c = st.columns([5.6, 3, 1.1])
        q = a.text_input("Busca", placeholder=t("🔎  Jogo, time, jogador ou competição — ex.: Brasil x Croácia, "
                         "Leverkusen, Messi, Premier League"), label_visibility="collapsed", key="global_q")
        b.multiselect(t("Nível de dado"), list(LEVEL_CHOICES), key="w_levels", format_func=t,
                      label_visibility="collapsed", placeholder=t("Nível de dado"),
                      help="Que jogos aparecem: 🟢 com lances e coordenadas, 📊 com estatísticas, 📄 só com o placar.")
        go = c.form_submit_button(t("Buscar"), type="primary", width="stretch")
    if go:
        picked = [LEVEL_CHOICES[k] for k in st.session_state.get("w_levels") or []]
        st.session_state["_levels"] = tuple(picked) or DEFAULT_LEVELS
        st.session_state["_last_q"] = (q or "").strip()
    _recent_matches()
    return (st.session_state.get("_last_q") or "").strip()


def _recent_matches() -> None:
    """Partidas abertas nesta sessão (só aparece se houver — nada é carregado de antemão)."""
    ids = st.session_state.get("recent_match_ids") or []
    if not ids:
        return
    from src.ui.context import load_bundle

    labels = {}
    for mid in ids[:5]:
        try:
            meta = load_bundle(int(mid)).meta or {}
            labels[f"{str(meta.get('match_date') or '')[:10]} · {meta.get('home_team_name', '?')} x "
                   f"{meta.get('away_team_name', '?')}"] = int(mid)
        except Exception:
            continue
    if labels:
        ra, rb = st.columns([5, 1])
        label = ra.selectbox("Partidas recentes", list(labels), key="til_recent_match", label_visibility="collapsed",
                             help="Últimas partidas abertas nesta sessão.")
        if rb.button("Reabrir", key="til_recent_open", width="stretch"):
            nav.open_view("jogo", match_id=labels[label])


def render(_ctx=None) -> None:
    from src.ui.context import analyzable_only, get_service

    q = search_box()
    if not q:
        hero("Buscar", "Um jogo, um time, um jogador ou uma competição",
             "Digite acima e aperte Enter ou Buscar. Clique no resultado para abrir a análise. Ao lado da busca, escolha "
             "que jogos aparecem: 🟢 com todos os lances, 📊 com estatísticas, 📄 só placar — ou os três.")
        _showcase()
        return
    from src.ui.context import chosen_levels

    version, only = get_service().db.stable_version(), "|".join(chosen_levels())   # níveis escolhidos no topo
    from src.ui.context import only_real

    with st.spinner("Procurando..."):                    # rodada 12: resultado guardado por busca (cliques não refazem)
        matches, teams, players, comps = _search_all(q.strip().lower(), version, only, only_real())
    if not teams.empty:                                  # rodada 14: pré-aquece a página dos 2 primeiros times
        _prewarm_teams(tuple(teams["nome"].head(2).astype(str)))
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
