"""🛡️ Tela do time — perfil, campanha, TODOS os jogos com dados (paginados), elenco e xG. Aberta pela busca única."""

from __future__ import annotations

from typing import List

import pandas as pd
import streamlit as st

from src.ui.perf import timed as _perf_timed

from src.ui.components import render_chart

from src.data_hub.registry import BADGES
from src.ui.components import comparison_table, empty_state, form_html, hero, result_card_html
from src.ui.crests import crest_img


@st.cache_data(show_spinner=False, ttl=900)
def _team_names(version: str) -> List[str]:
    from src.ui.context import cached_catalog

    c = cached_catalog()
    return sorted(pd.unique(pd.concat([c["home_team_name"], c["away_team_name"]]).dropna()))


_COUNTRY_KEYS = [
    ("ec", ("equador", "ecuador", "ligapro")), ("uy", ("uruguai", "uruguay")), ("ar", ("argentina", "primera nacional")),
    ("cl", ("chile",)), ("co", ("colômbia", "colombia")), ("pe", ("peru", "liga 1")), ("py", ("paraguai", "paraguay")),
    ("bo", ("bolívia", "bolivia")), ("ve", ("venezuela",)), ("mx", ("liga mx", "méxico", "mexico")),
    ("us", ("mls", "usa", "estados unidos")), ("br", ("brasil", "brasileir", "copa do brasil", "paulist", "carioca",
                                                     "mineiro", "gaúcho", "serie a brazil")),
    ("es", ("la liga", "laliga", "copa del rey", "espanha", "spain", "segunda división", "la liga 2")),
    ("en", ("premier league", "championship", "fa cup", "efl", "england", "inglaterra")),
    ("it", ("serie a", "serie b", "coppa italia", "itália", "italy")), ("de", ("bundesliga", "dfb", "alemanha", "germany")),
    ("fr", ("ligue 1", "ligue 2", "coupe de france", "frança", "france")), ("pt", ("primeira liga", "liga portugal",
                                                                                 "taça de portugal", "portugal")),
    ("nl", ("eredivisie", "eerste divisie", "knvb")), ("tr", ("süper lig", "super lig", "turquia", "turkey")),
]


def _comp_country(comp: str):
    c = str(comp or "").lower()
    if any(k in c for k in ("champions", "europa", "conference", "libertadores", "sul-americana", "sudamericana",
                            "mundial", "world", "amistoso", "friendl", "recopa", "supercopa da uefa", "super cup")):
        return None                                      # competição internacional: não diz o país
    return next((code for code, keys in _COUNTRY_KEYS if any(k in c for k in keys)), None)


@st.cache_data(show_spinner=False, max_entries=2)
def _name_countries(version: str) -> dict:
    """Nome do time → países das competições nacionais que ele disputa (pela base inteira, uma vez por versão)."""
    from src.ui.context import cached_catalog

    c = cached_catalog(include_score_only=True)
    if c.empty:
        return {}
    comp_c = {k: _comp_country(k) for k in c["competition_name"].dropna().unique()}
    # rodada 22: pares (time, competição) distintos primeiro — antes um laço Python por linha (600 mil, ~5 s)
    pairs = pd.concat([c[["home_team_name", "competition_name"]].set_axis(["n", "comp"], axis=1),
                       c[["away_team_name", "competition_name"]].set_axis(["n", "comp"], axis=1)]).dropna().drop_duplicates()
    pairs["cc"] = pairs["comp"].map(comp_c)
    pairs = pairs.dropna(subset=["cc"])
    out: dict = {}
    for n, cc in zip(pairs["n"].tolist(), pairs["cc"].tolist()):
        if isinstance(n, str):
            out.setdefault(n, set()).add(cc)
    return out


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
    # Identificadores geográficos/institucionais distintivos não podem ser descartados pelo fuzzy match.
    # Ex.: Santos FC e Santos Laguna compartilham "Santos", mas são clubes diferentes.
    import re as _re
    tokens = set(_re.findall(r"[a-z0-9]+", str(name).casefold()))
    distinctive = {"laguna", "unam", "pumas", "guadalajara", "monterrey", "tigres", "america", "medellin",
                   "cali", "quito", "cusco", "tijuana", "pachuca", "toluca"}
    identity = tokens & distinctive
    if identity:
        same = {n for n in same if identity.issubset(set(_re.findall(r"[a-z0-9]+", str(n).casefold())))}
    else:
        same = {n for n in same if not (set(_re.findall(r"[a-z0-9]+", str(n).casefold())) & distinctive)}
    # rodada 11: homônimos de países diferentes (Barcelona × Barcelona SC de Guayaquil; Liverpool × Liverpool de
    # Montevidéu) — pelo país das competições que cada nome disputa; e nome com palavra a mais que não é sufixo
    # ("RCD Espanyol de Barcelona") não é o mesmo time.
    from src.data_lake.ids import SUFFIXES

    countries = _name_countries(get_service().db.stable_version())
    mine = countries.get(name, set())
    base_toks = set(core.split())

    def compatible(n: str) -> bool:
        if n == name:
            return True
        other = countries.get(n, set())
        if mine and other and not (mine & other):
            return False
        ct = set(team_core(n).split())
        extra = (ct - base_toks) - SUFFIXES
        missing = (base_toks - ct) - SUFFIXES
        return team_core(n) == core or not (extra and missing) and not (extra and len(base_toks) == 1)
    same = {n for n in same if compatible(n)}
    # rodada 20: apelidos APRENDIDOS pelos jogos em comum entre fontes ("FC Cologne" na ESPN = "1. FC Köln" na FotMob)
    try:
        from src.data_hub.team_alias import aliases_of

        db = get_service().db
        learned = set()
        for n in list(same):
            learned |= set(aliases_of(db, n))
        for n in learned - same:                        # e as grafias que a normalização já liga a cada apelido
            learned |= set(t.loc[t["core"] == team_core(n), "nome"])
        same |= learned
    except Exception:
        pass
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
    # rodada 11: jogo de liga NACIONAL de outro país não é deste clube (homônimo com o mesmo nome em alguma fonte)
    cc = m["competition_name"].map(_comp_country)
    known = cc.dropna()
    if len(known) >= 10:
        share = known.value_counts(normalize=True)
        ok = set(share[share >= 0.2].index)
        m = m[cc.isna() | cc.isin(ok)]
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


def filter_team_matches(matches: pd.DataFrame, level: str = "Todos os jogos") -> pd.DataFrame:
    """Filtro explícito da profundidade do catálogo, sem depender do filtro global da navegação."""
    if matches is None or matches.empty or level == "Todos os jogos":
        return matches.copy() if matches is not None else pd.DataFrame()
    levels = {
        "Somente com lances": {"EVENTS"},
        "Com estatísticas ou lances (sem só placar)": {"EVENTS", "BOXSCORE"},
        "Somente com estatísticas": {"BOXSCORE"},
        "Somente placares": {"RESULT"},
    }
    allowed = levels.get(level)
    if allowed is None:
        raise ValueError(f"Filtro de partidas desconhecido: {level}")
    return matches[matches["data_level"].astype(str).isin(allowed)].copy()


def _open_next_match(team: str, rival: str) -> None:
    """Rodada 10: abre a Escalação já com o time e o adversário do próximo jogo (plano, provável e fragilidades)."""
    from src.ui import nav

    st.session_state["sq_team_q"] = team
    st.session_state["sq_rival_team"] = team
    st.session_state["sq_rival_choice"], st.session_state["sq_rival_src"] = rival, "próximo jogo"
    st.session_state.pop("sq_team_pick", None)
    nav.open_view("escalacao")
    st.rerun()


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


@st.cache_data(show_spinner=False, ttl=3600, max_entries=32)
def _roster_cached(names: tuple) -> pd.DataFrame:
    from src.squad.matchday import fotmob_roster
    from src.ui.context import get_service

    return fotmob_roster(get_service().db, list(names))


def _official_roster(name: str, names: List[str]) -> None:
    """Rodada 8: o elenco inscrito HOJE (FotMob) vem primeiro; o cadastro do Transfermarkt fica abaixo, como histórico."""
    with st.spinner("Buscando o elenco atual…"):
        r = _roster_cached(tuple(dict.fromkeys([name] + list(names))))
    if r.empty:
        st.caption("Elenco atual da FotMob indisponível para este clube — abaixo, o cadastro do Transfermarkt "
                   "(pode estar atrasado em relação à última janela).")
        return
    from datetime import date

    def _age(b):
        try:
            d = date.fromisoformat(str(b)[:10])
            t = date.today()
            return t.year - d.year - ((t.month, t.day) < (d.month, d.day))
        except Exception:
            return None
    order = {"keepers": 0, "defenders": 1, "midfielders": 2, "attackers": 3}
    t = r.assign(_o=r["role"].map(order).fillna(9), _n=pd.to_numeric(r["jersey"], errors="coerce")).sort_values(["_o", "_n"])
    view = pd.DataFrame({"nº": t["jersey"], "jogador": t["name"], "posição": t["position"],
                         "idade": t["birth"].map(_age), "altura (cm)": t["height"], "país": t["country"],
                         "valor (€ mi)": (pd.to_numeric(t["market_value"], errors="coerce") / 1e6).round(1),
                         "lesão": t["lesao"].replace("", "—")})
    st.markdown(f"##### 👥 Elenco atual — {len(view)} inscritos")
    comparison_table(view, f"Fonte: FotMob (lista do clube hoje, atualizada a cada 24 h; valor estimado pela FotMob). "
                           f"Atualizado em {str(t['fetched_at'].iloc[0])[:16].replace('T', ' ')} UTC.")


def render(_ctx=None) -> None:
    from src.ui import nav
    from src.ui.names import pt

    nav.back_button(key="team_back")
    name = nav.param("name")
    if not name:
        empty_state("Nenhum time escolhido", "Use o 🔎 Buscar e clique no time.", "🛡️")
        return
    names = same_team_names(name)
    # O perfil sempre carrega o catálogo completo uma única vez. O filtro local abaixo
    # permite alternar profundidade sem depender do seletor global e sem esconder placares.
    allm = team_matches(names, include_score_only=True)
    m = allm
    r = record(names, allm)
    lake, key, ids = _lake_team(name)
    fontes = sorted(ids["fonte"].unique()) if not ids.empty else sorted(allm["data_source"].unique()) if not allm.empty else []
    st.markdown(f'<div class="til-profile">{crest_img(name, "lg")}<div><div class="n">{pt(name)}</div>'
                f'<div class="d">{len(m)} jogos no nível escolhido · {len(allm)} resultados no total'
                + (f" · fontes: {', '.join(fontes)}" if fontes else "") + f'</div>{form_html(r.get("forma", []))}</div></div>',
                unsafe_allow_html=True)
    scout_a, scout_b = st.columns([1.8, 6])
    if scout_a.button("🎯 Planejar elenco", key=f"team_scout_{name}", type="primary", use_container_width=True):
        nav.open_view("scout", club=name)
    scout_b.caption("Diagnóstico de necessidades, alvos realistas e simulação de transferências.")
    k = st.columns(5)
    k[0].metric("Jogos (todos)", r.get("jogos", 0))
    k[1].metric("V / E / D", f"{r.get('V', 0)} / {r.get('E', 0)} / {r.get('D', 0)}")
    k[2].metric("Gols pró / contra", f"{r.get('gp', 0)} / {r.get('gc', 0)}")
    k[3].metric("Aproveitamento", f"{r.get('aprov', 0)}%")
    k[4].metric("Com todos os lances (✅)", int((allm["data_level"] == "EVENTS").sum()) if not allm.empty else 0)

    nxt = upcoming(names)
    if not nxt.empty:
        st.markdown("##### 📅 Próximos jogos")
        st.caption("Agenda do open-matchday (horário de início em CET-1, como a fonte publica).")
        comparison_table(nxt.head(5))
    t1, t0, t2, t3 = st.tabs(["🗓️ Jogos", "🧬 Estilo e tendências", "💶 Elenco e valores", "📈 Temporada (xG)"],
                             key="club_tabs", on_change="rerun")
    with t0:
        if t0.open is not False:          # rodada 21: só a aba aberta é montada
            _style_tab(name, names)
    with t1:
        if t1.open is not False:          # rodada 21: só a aba aberta é montada
            level_filter = st.selectbox(
                "Exibir partidas",
                ["Todos os jogos", "Com estatísticas ou lances (sem só placar)", "Somente com lances",
                 "Somente com estatísticas", "Somente placares"],
                key=f"team_level_filter_{name}",
                help="Filtro independente do seletor global. Todos os jogos inclui também partidas sem estatísticas ou eventos.",
            )
            m = filter_team_matches(allm, level_filter)
            if m.empty:
                empty_state("Nenhuma partida neste filtro", f"Há {len(allm)} resultado(s) deste time no catálogo. "
                            "Experimente 'Todos os jogos' ou outra profundidade de dados.", "🗓️")
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
        if t2.open is not False:          # rodada 21: só a aba aberta é montada
            _official_roster(name, names)
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
        if t3.open is not False:          # rodada 21: só a aba aberta é montada
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
                    render_chart(charts.lines(last.assign(jogo=last["data"] + " " + last["adversario"]), "jogo",
                                                 ["xg_pro", "xg_contra"], f"xG por jogo — últimos {len(last)}", "xG"),
                                    use_container_width=True)


@_perf_timed("clubs._style_data")
@st.cache_data(show_spinner=False, max_entries=48, persist="disk")  # rodada 14: sobrevive ao fechar o app
def _style_data(names: tuple, version: str) -> dict:
    from src.analytics import team_history as TH
    from src.ui.context import get_service

    db = get_service().db
    out = {"identidade": TH.identity(db, list(names), 15), "vulneraveis": TH.vulnerabilities(db, list(names), 15)}
    m = TH._matches(db, list(names), 15)
    v = TH._vectors(db, m, list(names))
    out["serie"] = v[["match_date", "home_team_name", "away_team_name", "home_score", "away_score", "f_xg", "c_xg",
                      "f_possession_pct"]].sort_values("match_date") if not v.empty else pd.DataFrame()
    from src.squad.matchday import next_fixtures

    out["proximos"] = next_fixtures(db, list(names), 5)
    return out


@_perf_timed("clubs._formation_data")
@st.cache_data(show_spinner=False, max_entries=48, persist="disk")  # rodada 14: sobrevive ao fechar o app
def _formation_data(names, version):
    from src.analytics.team_history import formation_patterns
    from src.ui.context import get_service

    return formation_patterns(get_service().db, list(names))


def _style_tab(name: str, names: List[str]) -> None:
    """Hub do clube (rodada 5): estilo habitual, problemas que se repetem, evolução do xG e próximos jogos."""
    import plotly.graph_objects as go

    from src.ui import charts
    from src.ui.context import get_service
    from src.ui.names import pt

    d = _style_data(tuple(names), get_service().db.team_version(names))
    idn, vu, ser = d["identidade"], d["vulneraveis"], d["serie"]
    card = lambda txt, c: st.markdown(f'<div class="fm-card" style="border-left:4px solid {c};border-radius:14px;padding:.6rem .9rem;'
                                      f'margin-bottom:.45rem">{txt}</div>', unsafe_allow_html=True)
    try:                                                 # rodada 13: o que cada desenho muda no ataque e na defesa
        fp = _formation_data(tuple(names), get_service().db.team_version(names))
        if fp.get("formacoes"):
            st.markdown("#### 🧩 Formações usadas: o que muda no ataque e na defesa")
            cols = st.columns(min(3, len(fp["formacoes"])))
            for i, f in enumerate(fp["formacoes"][:3]):
                with cols[i]:
                    att = "".join(f"<div style='font-size:.82rem'>⚔️ {x}</div>" for x in f["ataque"]) or \
                        "<div style='font-size:.82rem;color:#98A6BF'>ataque dentro do normal do time</div>"
                    dfn = "".join(f"<div style='font-size:.82rem;color:{'#86EFAC' if x.startswith('✓') else '#FCA5A5'}'>"
                                  f"🛡️ {x[2:]}</div>" for x in f["defesa"]) or \
                        "<div style='font-size:.82rem;color:#98A6BF'>defesa dentro do normal do time</div>"
                    card(f"<div style='font-size:1.25rem;font-weight:800;color:#22D3EE'>{f['formacao']}</div>"
                         f"<div style='color:#98A6BF;font-size:.82rem'>{f['jogos']} jogos · {f['pontos_por_jogo']} pts/jogo · "
                         f"gols {f['gols_pro']} × {f['gols_contra']}</div>{att}{dfn}", "#22D3EE")
            st.caption(fp.get("criterio", ""))
    except Exception:
        pass
    if ser is not None and not ser.empty:
        k = st.columns(4)
        xg_f, xg_c = pd.to_numeric(ser["f_xg"], errors="coerce"), pd.to_numeric(ser["c_xg"], errors="coerce")
        k[0].metric("xG a favor por jogo", f"{xg_f.mean():.2f}" if xg_f.notna().any() else "—")
        k[1].metric("xG contra por jogo", f"{xg_c.mean():.2f}" if xg_c.notna().any() else "—")
        pos = pd.to_numeric(ser["f_possession_pct"], errors="coerce")
        k[2].metric("Posse média", f"{pos.mean():.0f}%" if pos.notna().any() else "—")
        k[3].metric("Jogos com estatísticas", len(ser))
        if xg_f.notna().sum() >= 3:
            lab = [f"{r.match_date} · {pt(r.home_team_name)} {r.home_score}x{r.away_score} {pt(r.away_team_name)}" for r in ser.itertuples()]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=list(range(len(ser))), y=xg_f, mode="lines+markers", name="xG a favor",
                                     line=dict(color="#22D3EE", width=3), hovertext=lab, hoverinfo="text+y"))
            fig.add_trace(go.Scatter(x=list(range(len(ser))), y=xg_c, mode="lines+markers", name="xG contra",
                                     line=dict(color="#EF4444", width=3), hovertext=lab, hoverinfo="text+y"))
            fig.update_xaxes(showticklabels=False, title="jogos (do mais antigo ao mais recente)")
            render_chart(charts._layout(fig, "Evolução: chances criadas × cedidas (xG por jogo)", 320), use_container_width=True)
    a, b = st.columns(2)
    with a:
        st.markdown("#### 🧬 Como joga")
        for t_ in idn.get("tracos") or []:
            card(f"<b>{t_['traco'].capitalize()}</b><br><span style='color:#94A3B8'>{t_['metrica']}: {t_['media']} · normal "
                 f"{t_['referencia']} ({t_['dif_pct']:+.0f}%) · em {t_['frequencia_pct']}% dos jogos</span>", "#22D3EE")
        if not idn.get("tracos"):
            st.caption("Sem traço de estilo consistente nos jogos com estatísticas (ou poucos jogos).")
    with b:
        st.markdown("#### 🩹 Onde costuma sofrer")
        for p_ in vu.get("padroes") or []:
            card(f"<b>{p_['problema'].capitalize()}</b><br><span style='color:#94A3B8'>{p_['jogos_acima']} de {p_['jogos']} jogos acima "
                 f"do P70 da competição</span>", "#EF4444")
        for p_ in vu.get("sinais") or []:
            card(f"⚠️ {p_['problema'].capitalize()} <span style='color:#94A3B8'>— sinal, {p_['jogos_acima']} de {p_['jogos']} jogos</span>", "#F59E0B")
        if not (vu.get("padroes") or vu.get("sinais")):
            st.caption("Nenhum problema que se repita com frequência.")
    fx = d.get("proximos")
    if fx is not None and not fx.empty:
        st.markdown("#### 📅 Próximos jogos (ESPN/FotMob)")
        comparison_table(fx[["kickoff", "home", "away", "competition"]].rename(columns={
            "kickoff": "Início (UTC)", "home": "Mandante", "away": "Visitante", "competition": "Competição"}))
        f0 = fx.iloc[0]
        rival = f0["away"] if f0["home"] in names else f0["home"]
        if st.button(f"🔎 Analisar o próximo jogo ({f0['home']} x {f0['away']})", type="primary", key=f"club_next_{name}"):
            _open_next_match(name, rival)
