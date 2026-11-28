"""
Página Comparações:
  1. As duas equipes da partida lado a lado (indicadores, gols, destaques e redes de passes);
  2. Uma equipe comparada com ela mesma em outras partidas;
  3. Jogador × jogador — na partida aberta ou somando várias partidas de cada um (totais e por 90 min).
"""

from __future__ import annotations

import re

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from src.ui.components import render_chart

from src.data_hub.gender import gender_of
from src.data_hub.search import team_score
from src.metrics.match_facts import (PLAYER_STAT_LABELS, TEAM_STAT_LABELS, goal_line, goals, per90, player_match_stats,
                                     team_match_stats)
from src.ui import charts
from src.ui.components import comparison_table, empty_state, error_state, kpi, note, page_header, provenance_panel
from src.ui.context import MatchContext, get_service, load_bundle, processed_events

MAX_MATCHES = 40
MIN_MINUTES_PER90 = 90       # abaixo disso, valores por 90 min ficam instáveis
RADAR_KEYS = ["passes", "passes_progressivos", "passes_decisivos", "finalizacoes", "xg", "xt", "dribles",
              "desarmes", "interceptacoes", "recuperacoes"]
TEAM_KEYS = ["gols", "xg", "finalizacoes", "finalizacoes_no_alvo", "share_passes_pct", "field_tilt_pct", "ppda",
             "passes", "precisao_passe_pct", "passes_progressivos", "entradas_na_area", "cruzamentos", "escanteios",
             "recuperacoes", "perdas_de_posse", "xt", "faltas", "cartoes_amarelos"]


# ------------------------------------------------------------------ utilidades
def _label(r) -> str:
    hs, as_ = r.get("home_score"), r.get("away_score")
    sc = f"{int(hs)}–{int(as_)}" if pd.notna(hs) and pd.notna(as_) else "x"
    return f"{r.get('match_date') or '?'} · {r['home_team_name']} {sc} {r['away_team_name']} · {r['competition_name']}"


def _team_matches(team: str, gender: str) -> pd.DataFrame:
    """Partidas com eventos (StatsBomb/Wyscout) em que a equipe jogou, do mesmo gênero."""
    from src.ui.context import cached_catalog, filter_by_team

    cat = cached_catalog("data_level = 'EVENTS' AND data_source IN ('statsbomb','wyscout')")
    if cat.empty:
        return cat
    cat = cat[cat["genero"] == gender] if "genero" in cat.columns else cat
    found = filter_by_team(cat, team).sort_values("match_date", ascending=False).head(80).copy()
    if found.empty:
        return found
    ids = ",".join(str(int(m)) for m in found["match_id"])
    with get_service().db.connect() as conn:
        local = {r[0] for r in conn.execute(f"SELECT DISTINCT match_id FROM events WHERE match_id IN ({ids})")}
    found["no_banco"] = found["match_id"].isin(local)
    return found


def _options(found: pd.DataFrame, current: int, n_default: int):
    """Rótulos das partidas (✅ = eventos já no banco, abre na hora) e a seleção padrão: a atual + as locais mais recentes."""
    opts = {("✅ " if r.get("no_banco") else "⬇ ") + _label(r): int(r["match_id"]) for r in found.to_dict("records")}
    cur = [k for k, v in opts.items() if v == current][:1]
    local = [k for k, v in opts.items() if v != current and k.startswith("✅")]
    other = [k for k, v in opts.items() if v != current and not k.startswith("✅")]
    return opts, (cur + local + other)[:n_default]


@st.cache_data(show_spinner=False, ttl=900, max_entries=32)
def _load_processed(match_ids: List[int]) -> Dict[int, pd.DataFrame]:
    out: Dict[int, pd.DataFrame] = {}
    prog = st.progress(0.0, text="Carregando partidas...")
    for i, mid in enumerate(match_ids):
        try:
            b = load_bundle(int(mid))
            if b.events is not None and not b.events.empty:
                out[int(mid)] = processed_events(int(mid), b.events)[0]
        except Exception as exc:
            st.caption(f"Partida {mid} indisponível: {exc}")
        prog.progress((i + 1) / len(match_ids), text=f"Carregando partidas... {i + 1}/{len(match_ids)}")
    prog.empty()
    return out


def _canonical_team(df: pd.DataFrame, name: str) -> str:
    teams = df["team_name"].dropna().unique().tolist()
    return max(teams, key=lambda t: team_score(name, t)) if teams else name


# ------------------------------------------------------- 1. duas equipes
def _two_teams(ctx: MatchContext) -> None:
    a, b, df = ctx.target_team, ctx.opponent, ctx.df
    from src.ui.context import match_goals, match_player_stats, match_team_stats

    sa, sb = match_team_stats(ctx.match_id, a, df), match_team_stats(ctx.match_id, b, df)
    prov = ctx.prov("cmp_teams", f"{a} x {b}", "indicadores", "contagens dos eventos da partida (PPDA estimado)")
    gl = match_goals(ctx.match_id, df)
    k = st.columns(2)
    for col, t in zip(k, (a, b)):
        with col:
            lines = [goal_line(g) for g in gl if g["equipe"] == t]
            kpi(f"gols de {t}", sum(g["equipe"] == t for g in gl), prov)
            if lines:
                st.caption(" · ".join(lines))
    rows = pd.DataFrame([{"indicador": TEAM_STAT_LABELS[k_], a: sa.get(k_), b: sb.get(k_)} for k_ in TEAM_KEYS])
    l, r = st.columns([1.25, 1])
    with l:
        render_chart(charts.grouped_bars(rows[~rows["indicador"].isin(["Passes", "Perdas de posse"])], "indicador", [a, b],
                                            "Indicadores das duas equipes", height=620), width="stretch")
    with r:
        comparison_table(rows, "PPDA menor = pressão mais intensa. Posse = proporção dos passes da partida.")
    st.markdown("#### Destaques de cada equipe")
    pl = match_player_stats(ctx.match_id, None, df)
    cols = st.columns(2)
    for col, t in zip(cols, (a, b)):
        with col:
            p = pl[pl["equipe"] == t].sort_values("xt", ascending=False).head(6)
            comparison_table(p[["jogador", "posicao", "minutos", "gols", "assistencias", "finalizacoes", "passes",
                                "precisao_passe_pct", "xt"]].rename(columns=lambda c: PLAYER_STAT_LABELS.get(c, c)),
                             f"{t}: 6 maiores geradores de xT.")
    st.markdown("#### Redes de passes lado a lado")
    from src.networks.pass_network import PassingNetworkAnalyzer

    cols = st.columns(2)
    for col, t in zip(cols, (a, b)):
        try:
            net = PassingNetworkAnalyzer.build_pass_network(df, t, until_first_sub=True, min_pass_count=2)
            col.plotly_chart(charts.pass_network(net, f"{t} (até a 1ª substituição)"), width="stretch")
        except Exception as exc:
            with col:
                error_state(f"Rede de {t} indisponível", exc)


# ------------------------------------------------------- 2. equipe x ela mesma
def _team_over_time(ctx: MatchContext) -> None:
    gender = gender_of(ctx.bundle.meta or {})
    teams = [ctx.target_team, ctx.opponent]
    team = st.selectbox("Equipe", teams, key="cmp_self_team")
    found = _team_matches(team, gender)
    if found.empty:
        empty_state("Nenhuma outra partida com eventos desta equipe", "", "🔎",
                    "Sincronize a competição em Catálogo & Dados (StatsBomb/Wyscout).")
        return
    options, default = _options(found, ctx.match_id, 3)
    st.caption("✅ = eventos já no banco (abre na hora) · ⬇ = será baixada do StatsBomb/Wyscout")
    chosen = st.multiselect(f"Partidas de {team} (até {MAX_MATCHES})", list(options), default=default, key="cmp_self_matches")
    if len(chosen) < 2:
        empty_state("Escolha pelo menos duas partidas.", icon="📅")
        return
    key = ("self", team, tuple(chosen[:MAX_MATCHES]))
    if st.button("📊 Comparar estas partidas", type="primary", key="cmp_self_go"):
        st.session_state["cmp_self_key"] = key
    if st.session_state.get("cmp_self_key") != key:
        st.caption("Clique em “Comparar estas partidas” (as partidas que ainda não estão no banco são baixadas).")
        return
    data = _load_processed([options[c] for c in chosen[:MAX_MATCHES]])
    rows = []
    for c in chosen[:MAX_MATCHES]:
        df = data.get(options[c])
        if df is None:
            continue
        t = _canonical_team(df, team)
        opp = next((x for x in df["team_name"].dropna().unique() if x != t), "?")
        from src.ui.context import match_team_stats

        s = match_team_stats(options[c], t, df)
        rows.append({"partida": f"{c.split(' · ')[0]} x {opp}", **{TEAM_STAT_LABELS[k]: s.get(k) for k in TEAM_KEYS}})
    if len(rows) < 2:
        empty_state("Menos de duas partidas puderam ser carregadas.", icon="⚠️")
        return
    tab = pd.DataFrame(rows)
    ctx.prov("cmp_self", f"{team} em {len(rows)} partidas", len(rows), "team_match_stats por partida (mesmos cálculos)")
    pick = st.multiselect("Indicadores no gráfico", [TEAM_STAT_LABELS[k] for k in TEAM_KEYS],
                          default=["xG", "Finalizações", "Posse (% dos passes)", "Field tilt (%)"], key="cmp_self_ind")
    if pick:
        render_chart(charts.grouped_bars(tab.melt(id_vars="partida", value_vars=pick).pivot(index="variable", columns="partida",
                                                                                            values="value").reset_index(),
                                            "variable", tab["partida"].tolist(), f"{team}: indicadores por partida",
                                            height=120 + 70 * len(pick)), width="stretch")
    comparison_table(tab.set_index("partida").T.reset_index().rename(columns={"index": "indicador"}),
                     "Cada coluna é uma partida. Mesmo cálculo para todas, o que torna a comparação justa.")
    if len(rows) < 3:
        note("Amostra pequena", "Com duas partidas dá para comparar jogos, não para falar em tendência.", "warn")


# ------------------------------------------------------- 3. jogador x jogador
def _player_pool(ctx: MatchContext, label: str, key: str, default_idx: int):
    from src.ui.context import match_player_stats

    pl = match_player_stats(ctx.match_id, None, ctx.df)
    names = [f"{r.jogador} — {r.equipe}" for r in pl.itertuples()]
    if not names:
        return None, None
    choice = st.selectbox(label, names, index=min(default_idx, len(names) - 1), key=key)
    name, team = choice.split(" — ", 1)
    return name, team


def _player_totals(name: str, team: str, match_ids: List[int], data: Dict[int, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for mid in match_ids:
        df = data.get(mid)
        if df is None:
            continue
        from src.ui.context import match_player_stats

        s = match_player_stats(mid, None, df)
        r = s[s["jogador"] == name]
        if not r.empty:
            opp = next((x for x in df["team_name"].dropna().unique() if x != r.iloc[0]["equipe"]), "?")
            rows.append({"match_id": mid, "adversario": opp, **r.iloc[0].to_dict()})
    return pd.DataFrame(rows)


def _aggregate(per_match: pd.DataFrame) -> pd.Series:
    num = [c for c in PLAYER_STAT_LABELS if c in per_match.columns and c != "precisao_passe_pct"]
    tot = per_match[num].sum()
    tot["precisao_passe_pct"] = round(100 * tot["passes_certos"] / tot["passes"], 1) if tot["passes"] else None
    return tot


def _players(ctx: MatchContext) -> None:
    a, b = st.columns(2)
    with a:
        pa, ta = _player_pool(ctx, "Jogador A", "cmp_pa", 0)
    with b:
        pb, tb = _player_pool(ctx, "Jogador B", "cmp_pb", 1)
    if not pa or not pb:
        empty_state("Sem atletas nesta partida.")
        return
    scope = st.radio("Comparar em", ["Só nesta partida", "Várias partidas de cada um"], horizontal=True, key="cmp_scope")
    gender = gender_of(ctx.bundle.meta or {})
    picks = {pa: [ctx.match_id], pb: [ctx.match_id]}
    if scope != "Só nesta partida":
        c1, c2 = st.columns(2)
        for col, (p, t) in zip((c1, c2), ((pa, ta), (pb, tb))):
            with col:
                found = _team_matches(t, gender)
                opts, dflt = _options(found, ctx.match_id, 4)
                sel = st.multiselect(f"Partidas de {t} para {p}", list(opts), default=dflt, key=f"cmp_m_{p}")
                picks[p] = [opts[s] for s in sel[:MAX_MATCHES]] or [ctx.match_id]
        st.caption("O atleta só entra na conta das partidas em que aparece nos eventos (jogou).")
    ids = sorted(set(picks[pa]) | set(picks[pb]))
    if ids == [ctx.match_id]:
        data = {ctx.match_id: ctx.df}
    else:
        key = ("players", pa, pb, tuple(ids))
        if st.button("📊 Comparar os jogadores nestas partidas", type="primary", key="cmp_pl_go"):
            st.session_state["cmp_pl_key"] = key
        if st.session_state.get("cmp_pl_key") != key:
            st.caption("Clique em “Comparar os jogadores nestas partidas”.")
            return
        data = _load_processed(ids)
    pm_a, pm_b = _player_totals(pa, ta, picks[pa], data), _player_totals(pb, tb, picks[pb], data)
    if pm_a.empty or pm_b.empty:
        empty_state("Um dos atletas não aparece nas partidas escolhidas.", icon="👤")
        return
    tot_a, tot_b = _aggregate(pm_a), _aggregate(pm_b)
    prov = ctx.prov("cmp_players", f"{pa} x {pb}", f"{len(pm_a)} e {len(pm_b)} partidas",
                    "player_match_stats somado por atleta; por 90 = total × 90 ÷ minutos estimados")
    k = st.columns(4)
    with k[0]:
        kpi(f"partidas de {pa}", len(pm_a), prov)
    with k[1]:
        kpi(f"minutos de {pa}", int(tot_a["minutos"]), prov)
    with k[2]:
        kpi(f"partidas de {pb}", len(pm_b), prov)
    with k[3]:
        kpi(f"minutos de {pb}", int(tot_b["minutos"]), prov)
    p90a = per90(pd.DataFrame([tot_a]))
    p90b = per90(pd.DataFrame([tot_b]))
    low = [p for p, t in ((pa, tot_a), (pb, tot_b)) if t["minutos"] < MIN_MINUTES_PER90]
    if low:
        note("Amostra insuficiente para “por 90”", f"{', '.join(low)} tem menos de {MIN_MINUTES_PER90} minutos somados: "
             "compare os totais, não os valores por 90.", "warn")
    keys = [c for c in PLAYER_STAT_LABELS if c in tot_a.index]
    tab = pd.DataFrame([{"indicador": PLAYER_STAT_LABELS[c], f"{pa} (total)": tot_a[c], f"{pb} (total)": tot_b[c],
                         f"{pa} (por 90)": None if c in ("minutos", "precisao_passe_pct") else p90a.iloc[0][c],
                         f"{pb} (por 90)": None if c in ("minutos", "precisao_passe_pct") else p90b.iloc[0][c]} for c in keys])
    l, r = st.columns([1, 1.2])
    with l:
        mx = {c: max(float(p90a.iloc[0][c]), float(p90b.iloc[0][c]), 1e-6) for c in RADAR_KEYS}
        render_chart(charts.radar({pa: [round(100 * float(p90a.iloc[0][c]) / mx[c], 1) for c in RADAR_KEYS],
                                      pb: [round(100 * float(p90b.iloc[0][c]) / mx[c], 1) for c in RADAR_KEYS]},
                                     [PLAYER_STAT_LABELS[c] for c in RADAR_KEYS],
                                     f"Por 90 min (100 = o maior dos dois) · {int(tot_a['minutos'])} e {int(tot_b['minutos'])} min"),
                        width="stretch")
    with r:
        comparison_table(tab, "Minutos estimados pelas substituições. Assistência = último passe certo para o autor do gol.")
    if scope != "Só nesta partida":
        st.markdown("#### Partida a partida")
        show = ["adversario", "minutos", "gols", "assistencias", "finalizacoes", "xg", "passes", "precisao_passe_pct", "xt",
                "desarmes", "recuperacoes"]
        x, y = st.columns(2)
        with x:
            comparison_table(pm_a[show].rename(columns=lambda c: PLAYER_STAT_LABELS.get(c, c)), pa)
        with y:
            comparison_table(pm_b[show].rename(columns=lambda c: PLAYER_STAT_LABELS.get(c, c)), pb)


def render(ctx: MatchContext) -> None:
    page_header("🆚 Comparações", "As duas equipes ao mesmo tempo, a equipe contra ela mesma e jogador contra jogador.", ctx)
    if not ctx.has_events:
        empty_state("Esta página precisa de eventos", "", "🆚", "Escolha uma partida ✅ (eventos) na barra lateral.")
        return
    modes = {f"⚔️ {ctx.target_team} x {ctx.opponent}": _two_teams, "📅 Equipe x ela mesma": _team_over_time,
             "👥 Jogador x jogador": _players}
    pick = st.radio("Comparação", list(modes), horizontal=True, key="cmp_mode", label_visibility="collapsed")
    try:
        modes[pick](ctx)
    except Exception as exc:
        error_state("Comparação indisponível", exc)
    provenance_panel(ctx.registry)


# =========================================================== página Comparar (todos os modos)
def _club_vs_club() -> None:
    from src.ui.components import form_html
    from src.ui.crests import crest_img
    from src.ui.pages.clubs import _lake_team, _team_names, record, team_matches
    from src.ui.context import filter_by_team, get_service

    names = _team_names(get_service().db.stable_version())
    pool = pd.DataFrame({"home_team_name": names, "away_team_name": names})
    a, b = st.columns(2)
    qa = a.text_input("Clube A", "Flamengo", key="cc_a")
    qb = b.text_input("Clube B", "Palmeiras", key="cc_b")
    picks = []
    for col, q, key in ((a, qa, "cc_sa"), (b, qb, "cc_sb")):
        cand = filter_by_team(pool, q, 0.86)["home_team_name"].tolist() if q.strip() else []
        cand = sorted(cand, key=lambda n: -len(team_matches(n)))[:15]
        picks.append(col.selectbox("Escolha", cand, key=key) if cand else None)
    if not all(picks):
        empty_state("Escolha os dois clubes", icon="🛡️")
        return
    ta, tb = picks
    ma, mb = team_matches(ta, include_score_only=True), team_matches(tb, include_score_only=True)   # retrospecto: todos os resultados
    ra, rb = record(ta, ma.head(38)), record(tb, mb.head(38))
    c1, c2 = st.columns(2)
    for col, t, r in ((c1, ta, ra), (c2, tb, rb)):
        col.markdown(f'<div class="til-profile">{crest_img(t, "lg")}<div><div class="n">{t}</div>'
                     f'<div class="d">últimos {r.get("jogos", 0)} jogos com placar</div>{form_html(r.get("forma", []))}</div></div>',
                     unsafe_allow_html=True)
    rows = []
    for lab, k in (("Jogos", "jogos"), ("Vitórias", "V"), ("Empates", "E"), ("Derrotas", "D"), ("Gols pró", "gp"),
                   ("Gols contra", "gc"), ("Aproveitamento (%)", "aprov")):
        rows.append({"indicador": lab, ta: ra.get(k), tb: rb.get(k)})
    from src.ui.components import duel_bars

    duel_bars([{"label": r["indicador"], "a": r[ta], "b": r[tb], "fmt": "{:.0f}",
                "lower_is_better": r["indicador"] in ("Derrotas", "Gols contra")} for r in rows if r["indicador"] != "Jogos"],
              ta, tb, "Últimos 38 jogos com placar (todas as competições)")
    h2h = ma[((ma["home_team_name"] == ta) & (ma["away_team_name"] == tb)) | ((ma["home_team_name"] == tb) & (ma["away_team_name"] == ta))]
    st.markdown(f"##### Confronto direto: {len(h2h)} jogo(s) no catálogo")
    if not h2h.empty:
        rh = record(ta, h2h)
        st.caption(f"{ta}: {rh['V']} vitórias · {rh['E']} empates · {rh['D']} derrotas · gols {rh['gp']} x {rh['gc']}")
        from src.data_hub.registry import BADGES
        from src.ui.components import result_card_html

        for row in h2h.head(10).to_dict("records"):
            st.markdown(result_card_html(row, BADGES.get(row["data_level"], "")), unsafe_allow_html=True)
    lake, ka, ida = _lake_team(ta)
    _, kb, idb = _lake_team(tb)
    if lake is not None and lake.exists("tm_jogadores") and not ida.empty and not idb.empty:
        tm = lake.read("tm_jogadores")
        val = {}
        for t, ids in ((ta, ida), (tb, idb)):
            tid = ids[ids["fonte"] == "transfermarkt"]["id_fonte"].astype(str).tolist()
            val[t] = round(tm[tm["clube_id"].astype(str).isin(tid)]["valor_mercado_eur"].fillna(0).sum() / 1e6, 1)
        if any(val.values()):
            x = st.columns(2)
            for col, t in zip(x, (ta, tb)):
                col.metric(f"Valor do elenco — {t} (€ mi, Transfermarkt)", val[t])


def _match_vs_match() -> None:
    from src.data_hub.registry import BADGES
    from src.ui.components import result_card_html
    from src.ui.context import get_service, load_bundle, match_team_stats, processed_events

    cols = st.columns(2)
    chosen = []
    for col, key, default in ((cols[0], "mm_a", "Argentina x França 2022"), (cols[1], "mm_b", "Argentina x Croácia 2022")):
        q = col.text_input("Jogo", default, key=key)
        res = get_service().finder.find(q, allow_remote=False) if q.strip() else {"candidates": pd.DataFrame()}
        c = res["candidates"] if not res["candidates"].empty else res.get("suggestions", pd.DataFrame())
        if c is None or c.empty:
            col.caption("Nenhum jogo encontrado.")
            chosen.append(None)
            continue
        from src.ui.pages.search_all import one_per_game

        c = one_per_game(c)                          # rodada 8: o mesmo jogo de duas fontes aparece uma vez
        opts = c.head(8).to_dict("records")
        i = col.selectbox("Resultado", range(len(opts)), key=key + "_s",
                          format_func=lambda j: f"{opts[j]['match_date']} · {opts[j]['home_team_name']} x {opts[j]['away_team_name']}")
        col.markdown(result_card_html(opts[i], BADGES.get(opts[i]["data_level"], "")), unsafe_allow_html=True)
        chosen.append(opts[i])
    if not all(chosen):
        return
    rows, labels = [], []
    for m in chosen:
        b = load_bundle(int(m["match_id"]))
        label = f"{m['home_team_name']} x {m['away_team_name']} ({str(m['match_date'])[:4]})"
        labels.append(label)
        if b.events is not None and not b.events.empty:
            df = processed_events(int(m["match_id"]), b.events)[0]
            for side in ("home_team_name", "away_team_name"):
                s = match_team_stats(int(m["match_id"]), m[side], df)
                rows.append({"jogo": label, "equipe": m[side], **{TEAM_STAT_LABELS[k]: s.get(k) for k in TEAM_KEYS}})
        else:
            st_ = (b.boxscore or {}).get("team_stats", pd.DataFrame())
            for side in ("home_team_name", "away_team_name"):
                r = {"jogo": label, "equipe": m[side], "Gols": m["home_score"] if side == "home_team_name" else m["away_score"]}
                if st_ is not None and not st_.empty:
                    for x in st_[st_["team_name"] == m[side]].itertuples():
                        r[x.stat_label] = x.value
                rows.append(r)
    tab = pd.DataFrame(rows)
    comparison_table(tab.set_index(["jogo", "equipe"]).T.reset_index().rename(columns={"index": "indicador"}),
                     "Jogos com eventos (✅) têm todos os indicadores; os demais, o que a fonte publica.")


# ------------------------------------------------------------------ v36: qualquer jogador × qualquer jogador
RECORTES = {"Último jogo": 1, "Últimos 5 jogos": 5, "Últimos 10 jogos": 10, "Últimos 20 jogos": 20,
            "Últimos 40 jogos": 40, "Temporada mais recente": None}


@st.cache_data(show_spinner=False, ttl=900, max_entries=64)
def _match_dates(ids: tuple) -> pd.DataFrame:
    from src.ui.context import get_service

    if not ids:
        return pd.DataFrame(columns=["match_id", "match_date", "season_name", "competition_name"])
    ph = ",".join("?" * len(ids))
    with get_service().db.connect() as conn:
        return pd.read_sql_query(f"SELECT match_id, match_date, season_name, competition_name, home_team_name, "
                                 f"away_team_name FROM matches WHERE match_id IN ({ph})", conn, params=list(ids))


def player_cut(per_match: pd.DataFrame, dates: pd.DataFrame, recorte: str) -> pd.DataFrame:
    """Jogos do recorte (só partidas com lances do jogador): último, últimos 5 ou a temporada mais recente."""
    if per_match is None or per_match.empty:
        return pd.DataFrame()
    m = per_match.merge(dates, on="match_id", how="left").sort_values("match_date", ascending=False)
    n = RECORTES.get(recorte)
    if n:
        return m.head(n)
    season = m["season_name"].dropna().astype(str)
    return m[m["season_name"].astype(str) == season.iloc[0]] if not season.empty else m.head(0)


def _player_pick(label: str, key: str):
    from src.ui.context import get_service
    from src.ui.pages.players_search import player_index
    from src.ui.pages.search_all import find_players

    q = st.text_input(label, key=f"{key}_q", placeholder="nome do jogador (ex.: Messi, Vinícius)")
    if len(q.strip()) < 3:
        return None, []
    version = get_service().db.stable_version()
    found = find_players(q, version, n=10)
    if found.empty:
        st.caption("Nenhum jogador com esse nome.")
        return None, []
    opts = found.to_dict("records")
    r = st.selectbox("Escolha", opts, key=f"{key}_pick", label_visibility="collapsed",
                     format_func=lambda x: f"{x['nome']}" + (f" · {x['clube']}" if x.get("clube") else "")
                     + (f" · {int(x['jogos'])} jogos indexados" if pd.notna(x.get("jogos")) and x.get("jogos") else ""))
    idx = player_index(version)
    names = idx.loc[(idx["pessoa"] == r["core"]) & (idx["fonte"].str.startswith("eventos")), "nome"].unique().tolist()
    return r, names


FM_GROUPS = {
    "⚽ Ataque": [("totalGoals", "Gols", False), ("xg", "xG", False), ("totalShots", "Finalizações", False),
                 ("shotsOnTarget", "No alvo", False), ("touches_opp_box", "Toques na área rival", False)],
    "🎯 Criação e passe": [("goalAssists", "Assistências", False), ("xa", "xA", False), ("chances_created", "Chances criadas", False),
                          ("passes_into_final_third", "Passes no terço final", False), ("line_breaking_passes", "Quebram linhas", False),
                          ("accurate_crosses", "Cruzamentos certos", False), ("accurate_passes", "Passes certos", False)],
    "🏃 Progressão": [("dribbles_succeeded", "Dribles certos", False), ("touches", "Toques na bola", False),
                     ("dispossessed", "Perdeu a posse", True)],
    "🛡️ Defesa e duelos": [("matchstats.headers.tackles", "Desarmes", False), ("interceptions", "Interceptações", False),
                          ("recoveries", "Recuperações", False), ("clearances", "Cortes", False), ("duel_won", "Duelos ganhos", False),
                          ("aerials_won", "Aéreos ganhos", False), ("dribbled_past", "Vezes driblado", True),
                          ("foulsCommitted", "Faltas cometidas", True)],
    "📡 Físico (só ligas que medem)": [("distance_m", "Distância (m)", False), ("sprints", "Sprints", False)],
}


_NAME_VARIANTS: Dict[str, Any] = {}


def name_variants(db, names) -> list:
    """Rodada 25b: todas as grafias do banco com o mesmo núcleo de nome ("Gerson" × "Gérson"). Antes a consulta
    buscava só a grafia exata e o Gerson do Cruzeiro aparecia com 1 jogo."""
    from src.data_lake.ids import player_core

    if "map" not in _NAME_VARIANTS:
        try:
            with db.connect() as conn:
                allnames = [r[0] for r in conn.execute("SELECT DISTINCT player_name FROM match_player_stats "
                                                       "WHERE player_name IS NOT NULL")]
        except Exception:
            allnames = []
        m: Dict[str, list] = {}
        for n in allnames:
            m.setdefault(player_core(n), []).append(n)
        _NAME_VARIANTS["map"] = m
    m = _NAME_VARIANTS["map"]
    out = list(names)
    for n in names:
        out += m.get(player_core(n), [])
    return list(dict.fromkeys(out))


@st.cache_data(show_spinner=False, ttl=1800, max_entries=64)
def _fotmob_player(names: tuple, n_games: int, version: str, club: str = "") -> Dict[str, Any]:
    """Números da FotMob do jogador (identidade pelo id do atleta da FotMob), somados nos últimos `n_games` jogos."""
    import json as _j

    from src.ui.context import get_service

    if not names:
        return {}
    names = tuple(name_variants(get_service().db, names))
    # rodada 12: também as grafias parecidas ("Lucas Romero" ⊂ "Lucas Daniel Romero"): primeiro e último nome
    import unicodedata as _u

    def fold(x):
        return _u.normalize("NFKD", str(x).lower()).encode("ascii", "ignore").decode()
    likes = []
    for nm in names:
        toks = [t for t in fold(nm).split() if len(t) >= 3]
        if len(toks) >= 2:
            likes.append((f"%{toks[0]}%{toks[-1]}%", toks))
    ph = ",".join("?" * len(names))
    extra = " OR ".join("LOWER(s.player_name) LIKE ?" for _ in likes)
    with get_service().db.connect() as conn:
        d = pd.read_sql_query(f"SELECT s.match_id, s.player_name, s.team_name, s.rating, s.stats_json, m.match_date, m.season_name "
                              f"FROM match_player_stats s JOIN matches m ON m.match_id = s.match_id "
                              f"WHERE (s.player_name IN ({ph}){' OR ' + extra if extra else ''}) AND m.data_source = 'fotmob' "
                              f"ORDER BY m.match_date DESC LIMIT 4000", conn,
                              params=list(names) + [lk for lk, _ in likes])
    if d.empty:
        return {}
    if likes:                                            # LIKE sem acento pode trazer "Lucas Romeroso": confere os tokens
        d = d[[n in names or any(all(t in fold(n).split() for t in toks) for _, toks in likes) for n in d["player_name"]]]
        if d.empty:
            return {}
    d["st"] = [_j.loads(x or "{}") for x in d["stats_json"]]
    d["fid"] = [s.get("fotmob_id") or f"{p}|{t}" for s, p, t in zip(d["st"], d["player_name"], d["team_name"])]
    # o atleta certo é o que MAIS jogou no último ano (não o da linha mais recente, que pode ser um homônimo)
    recent = pd.to_datetime(d["match_date"], errors="coerce") >= pd.Timestamp.today() - pd.Timedelta(days=365)
    counts = d[recent].groupby("fid").size() if recent.any() else d.groupby("fid").size()
    best = counts.idxmax()
    if club:                                             # rodada 25b: homônimo → o atleta que jogou pelo clube escolhido
        from src.data_lake.ids import team_core

        try:
            from src.ui.pages.clubs import same_team_names

            cores = {team_core(x) for x in same_team_names(club)} | {team_core(club)}
        except Exception:
            cores = {team_core(club)}
        at_club = d[d["team_name"].map(lambda t: team_core(str(t)) in cores)]
        if not at_club.empty:
            best = at_club.groupby("fid").size().idxmax()
    others = [f"{g['player_name'].iloc[0]} ({g['team_name'].iloc[0]}, {len(g)} jogos)"
              for fid, g in d.groupby("fid") if fid != best][:3]
    d = d[d["fid"] == best]
    top = d.iloc[0]
    d = d[[bool(s.get("minutes")) for s in d["st"]]]
    season_label = None
    if int(n_games or 0) <= 0 and not d.empty:
        # rodada 22: "Temporada mais recente" = todos os jogos (todas as competições) desde o início da temporada do jogo
        # mais recente — antes caía em "últimos 40 jogos". Temporada "2026-2027" começa em 1º/7; "2026", em 1º/1.
        sn = str(d["season_name"].iloc[0] or "")
        y0 = re.match(r"(\d{4})", sn)
        if y0:
            start = f"{y0.group(1)}-07-01" if re.match(r"\d{4}\s*[-/]\s*\d{2,4}", sn) else f"{y0.group(1)}-01-01"
            d = d[d["match_date"].astype(str) >= start]
            season_label = f"temporada {sn.replace('-', '/')} (desde {start[8:10]}/{start[5:7]}/{start[:4]}, todas as competições)"
        else:
            d = d.head(40)
    else:
        d = d.head(int(n_games))
    if d.empty:
        return {}
    tot: Dict[str, float] = {}
    mins_k: Dict[str, float] = {}                    # minutos SÓ dos jogos em que aquele número foi medido
    games_k: Dict[str, int] = {}
    for s in d["st"]:
        m = float(s.get("minutes") or 0)
        for k, v in s.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("fotmob_id", "minutes"):
                tot[k] = tot.get(k, 0.0) + float(v)
                mins_k[k] = mins_k.get(k, 0.0) + m
                games_k[k] = games_k.get(k, 0) + 1
    mins = float(sum(float(s.get("minutes") or 0) for s in d["st"])) or 1
    # rodada 7: antes tudo era dividido pelos minutos de TODOS os jogos — distância/sprints (medidos só em algumas
    # ligas/jogos) saíam irreais (ex.: 2.744 m por 90). Agora cada número usa os minutos dos jogos em que existe.
    per90 = {k: v * 90 / mins_k[k] for k, v in tot.items() if mins_k.get(k)}
    rat = pd.to_numeric(d["rating"], errors="coerce").dropna()
    return {"jogos": int(len(d)), "minutos": int(mins), "per90": per90, "jogos_por_numero": games_k,
            "minutos_por_numero": {k: int(v) for k, v in mins_k.items()},
            "nota_fotmob": round(float(rat.mean()), 2) if len(rat) else None,
            "time": top["team_name"], "ultimo": str(d["match_date"].iloc[0]), "nome_fonte": top["player_name"],
            "homonimos": others, "totais": tot, "recorte_txt": season_label}


def _fotmob_compare(pa, na, pb, nb, recorte: str) -> None:
    from src.ui.components import duel_bars
    from src.ui.context import get_service

    if not (pa and pb):
        return
    n_games = RECORTES.get(recorte) or 0                # 0 = temporada inteira (rodada 22)
    v = get_service().db.stable_version()
    A = _fotmob_player(tuple(dict.fromkeys((na or []) + [pa["nome"]])), n_games, v, str(pa.get("clube") or ""))
    B = _fotmob_player(tuple(dict.fromkeys((nb or []) + [pb["nome"]])), n_games, v, str(pb.get("clube") or ""))
    if not (A and B):
        missing = [p["nome"] for p, X in ((pa, A), (pb, B)) if not X]
        st.caption(f"📊 Sem números da FotMob para: {', '.join(missing)} (a base ainda está sendo abastecida).")
        return
    n1, n2 = pa["nome"], pb["nome"]
    from src.ui.components import versus_hero          # rodada 22: cabeçalho lado a lado

    def _sel(X):
        return {"Jogos": X.get("jogos"), "Min": X.get("minutos"), "Nota FotMob": X.get("nota_fotmob")}
    versus_hero({"nome": n1, "meta": f"{A.get('time') or ''} · último jogo {str(A.get('ultimo') or '')[:10]}", "selos": _sel(A)},
                {"nome": n2, "meta": f"{B.get('time') or ''} · último jogo {str(B.get('ultimo') or '')[:10]}", "selos": _sel(B)})
    st.markdown("#### 📊 Pelos números por jogador da FotMob (muito mais jogos)")
    single = int(n_games) == 1 or (A["jogos"] == 1 and B["jogos"] == 1)
    unit = "no jogo (total)" if single else "por 90 minutos"
    st.markdown(f'<div style="color:#98A6BF;font-size:.8rem">{n1}: {A["jogos"]} jogo(s), {A["minutos"]} min '
                f'({A["time"]}, último {A["ultimo"]}) · {n2}: {B["jogos"]} jogo(s), {B["minutos"]} min '
                f'({B["time"]}, último {B["ultimo"]}) · {unit}. Minutagem é critério de desempate.'
                + (f' Recorte: {A["recorte_txt"]}.' if A.get("recorte_txt") else "") + '</div>',
                unsafe_allow_html=True)
    for who, X in ((n1, A), (n2, B)):
        if X.get("homonimos"):
            st.caption(f"{who}: usado o atleta com mais jogos no último ano ({X.get('nome_fonte')}). Nome parecido, "
                       f"outra pessoa: " + "; ".join(X["homonimos"]) + ".")
    TA, TB = A.get("totais") or {}, B.get("totais") or {}
    # aba de resumo (totais — gols e assistências não se leem por 90) e aproveitamento (%), depois os blocos por 90
    def pct(T, ok, tot):
        return 100 * T[ok] / T[tot] if T.get(tot) else None
    summary = [("Jogos", A["jogos"], B["jogos"], False, "{:.0f}"), ("Minutos", A["minutos"], B["minutos"], False, "{:.0f}"),
               ("Gols", TA.get("totalGoals"), TB.get("totalGoals"), False, "{:.0f}"),
               ("Assistências", TA.get("goalAssists"), TB.get("goalAssists"), False, "{:.0f}"),
               ("Cartões amarelos", TA.get("yellowCards"), TB.get("yellowCards"), True, "{:.0f}"),
               ("Nota média (FotMob)", A.get("nota_fotmob"), B.get("nota_fotmob"), False, "{:.2f}")]
    rates = [("Acerto de passe (%)", pct(TA, "accurate_passes", "accurate_passes_total"), pct(TB, "accurate_passes", "accurate_passes_total")),
             ("Duelos ganhos (%)", pct({**TA, "_d": TA.get("duel_won", 0) + TA.get("duel_lost", 0)}, "duel_won", "_d"),
              pct({**TB, "_d": TB.get("duel_won", 0) + TB.get("duel_lost", 0)}, "duel_won", "_d")),
             ("Aéreos ganhos (%)", pct(TA, "aerials_won", "aerials_won_total"), pct(TB, "aerials_won", "aerials_won_total")),
             ("Dribles certos (%)", pct(TA, "dribbles_succeeded", "dribbles_succeeded_total"),
              pct(TB, "dribbles_succeeded", "dribbles_succeeded_total")),
             ("Bolas longas certas (%)", pct(TA, "long_balls_accurate", "long_balls_accurate_total"),
              pct(TB, "long_balls_accurate", "long_balls_accurate_total"))]
    wins = {n1: 0, n2: 0}
    tabs = st.tabs(["📋 Resumo", "🎯 Aproveitamento (%)"] + list(FM_GROUPS))
    with tabs[0]:
        rows0 = [{"label": l, "a": a, "b": b, "fmt": f, "lower_is_better": low} for l, a, b, low, f in summary
                 if a is not None and b is not None]
        if rows0:
            duel_bars(rows0, n1, n2, "Resumo (totais do recorte)")
    with tabs[1]:
        rows1 = [{"label": l, "a": a, "b": b, "fmt": "{:.0f}", "lower_is_better": False} for l, a, b in rates
                 if a is not None and b is not None]
        if rows1:
            duel_bars(rows1, n1, n2, "Aproveitamento — o que deu certo do que tentou")
        else:
            st.caption("A fonte não publica tentativas e acertos para esses jogos.")
    for tab, (g, items) in zip(tabs[2:], FM_GROUPS.items()):
        src_a, src_b = (TA, TB) if single else (A["per90"], B["per90"])
        rows = [{"label": lab, "a": src_a.get(k), "b": src_b.get(k), "fmt": "{:.0f}" if single else "{:.2f}",
                 "lower_is_better": low}
                for k, lab, low in items if src_a.get(k) is not None and src_b.get(k) is not None]
        for r in rows:
            if r["a"] != r["b"]:
                wins[n1 if (r["a"] > r["b"]) != r["lower_is_better"] else n2] += 1
        with tab:
            if rows:
                duel_bars(rows, n1, n2, f"{g} — {unit}")
                if g.startswith("📡"):
                    ja, jb = A["jogos_por_numero"], B["jogos_por_numero"]
                    st.caption("Por 90 calculado só nos jogos em que a liga mediu: " + " · ".join(
                        f"{lab}: {n1} {ja.get(k, 0)} jogo(s) / {n2} {jb.get(k, 0)} jogo(s)" for k, lab, _ in items
                        if k in ja or k in jb) + ".")
            else:
                st.caption("A fonte não publica esses números para os jogos deles (não é zero).")
    na_, nb_ = A.get("nota_fotmob"), B.get("nota_fotmob")
    st.markdown(f'<div class="til-card" style="min-height:auto"><div class="label">Placar dos indicadores (FotMob)'
                + (f" · nota média FotMob {na_} × {nb_}" if na_ and nb_ else "") + '</div>'
                f'<div class="value" style="font-size:1.6rem"><span style="color:#22D3EE">{n1} {wins[n1]}</span> × '
                f'<span style="color:#EF4444">{wins[n2]} {n2}</span></div></div>', unsafe_allow_html=True)


def _any_players() -> None:
    """Comparação por camada de dado: boxscore amplo ou eventos com coordenadas."""
    from src.ui.pages.players_search import SCOUT_GROUPS, player_scout

    st.caption("Selecione qualquer atleta indexado. A disponibilidade de cada camada é mostrada separadamente; "
               "um jogo com boxscore não é tratado como jogo com eventos e coordenadas.")
    a, b = st.columns(2)
    with a:
        pa, na = _player_pick("Jogador A", "cmpA")
    with b:
        pb, nb = _player_pick("Jogador B", "cmpB")
    from src.ui.i18n import t

    recorte = st.radio(t("Recorte"), list(RECORTES), horizontal=True, key="cmp_any_cut",
                       index=list(RECORTES).index("Temporada mais recente"), format_func=t)   # rodada 22: visão conjunta
    depth = st.radio("Camada de dados", ["Dados estatísticos (FotMob/boxscore)", "Dados detalhados (eventos)",
                                         "Visão conjunta"], horizontal=True, key="cmp_any_depth")
    if not (pa and pb):
        empty_state("Escolha os dois jogadores", "Digite pelo menos 3 letras de cada nome.", "👥")
        return

    if depth in ("Dados estatísticos (FotMob/boxscore)", "Visão conjunta"):
        _fotmob_compare(pa, na, pb, nb, recorte)

    if depth in ("Dados detalhados (eventos)", "Visão conjunta"):
        cols, info = {}, []
        for p, names in ((pa, na), (pb, nb)):
            sc = player_scout(tuple(names)) if names else pd.DataFrame()
            if sc.empty:
                info.append(f"**{p['nome']}**: sem jogos com eventos e coordenadas na base.")
                continue
            cut = player_cut(sc.fillna(0), _match_dates(tuple(int(x) for x in sc["match_id"])), recorte)
            if cut.empty:
                info.append(f"**{p['nome']}**: nenhum jogo com eventos no recorte escolhido.")
                continue
            mins = float((cut["m1"] - cut["m0"]).clip(lower=1, upper=125).sum())
            per = {k: float(cut[k].sum()) / max(mins, 1) * 90
                   for g in SCOUT_GROUPS.values() for k, _ in g if k in cut}
            cols[p["nome"]] = per
            last = cut.iloc[0]
            info.append(f"**{p['nome']}**: {len(cut)} jogo(s) com eventos, ~{mins:.0f} min estimados · "
                        f"último: {last.get('match_date')} {last.get('home_team_name', '')} x {last.get('away_team_name', '')}")
        st.markdown("#### 🧭 Camada detalhada — eventos com coordenadas")
        for line in info:
            st.markdown("- " + line)
        if len(cols) == 2:
            from src.ui.components import duel_bars

            (n1, v1), (n2, v2) = list(cols.items())
            worse = {"perdas_de_posse", "faltas_cometidas", "amarelos", "vermelhos", "erros"}
            wins = {n1: 0, n2: 0}
            tabs = st.tabs([{"Atacando": "⚽ Ataque", "Passe": "🎯 Passe", "Defendendo": "🛡️ Defesa",
                             "Outros": "⚔️ Duelos e disciplina"}.get(g, g) for g in SCOUT_GROUPS])
            for tab, (g, items) in zip(tabs, SCOUT_GROUPS.items()):
                rows = [{"label": lab, "a": v1[k], "b": v2[k], "fmt": "{:.2f}", "lower_is_better": k in worse}
                        for k, lab in items if k in v1 and k in v2]
                for r in rows:
                    if r["a"] != r["b"]:
                        wins[n1 if (r["a"] > r["b"]) != r["lower_is_better"] else n2] += 1
                with tab:
                    if rows:
                        duel_bars(rows, n1, n2, f"{g} — {unit}")
                    else:
                        st.caption("Sem indicadores comparáveis nessa categoria.")
            st.markdown(f"**Placar dos indicadores de eventos:** {n1} {wins[n1]} × {wins[n2]} {n2}")
            st.caption("Minutos estimados pelo intervalo entre a primeira e a última ação do atleta em cada jogo. "
                       "Esta camada não representa tracking contínuo nem todos os jogos da carreira.")


def render_page(current_context, match_bar) -> None:
    from src.ui.components import hero

    hero("Comparar", "Lado a lado", "Jogador × jogador, jogo × jogo, clube × clube, a equipe contra ela mesma ou as duas "
         "equipes da partida aberta.")
    modes = ["👥 Jogador × jogador", "🏟️ Jogo × jogo", "🛡️ Clube × clube", "📅 Equipe × ela mesma", "⚔️ Duas equipes da partida"]
    from src.ui.i18n import t

    pick = st.radio("Modo", modes, horizontal=True, key="cmp_page_mode", label_visibility="collapsed", format_func=t)
    if pick == modes[0]:
        src = st.radio("Jogadores", ["De qualquer jogo da base", "Da partida aberta"], horizontal=True, key="cmp_any_src",
                       format_func=t)
        if src == "De qualquer jogo da base":
            try:
                _any_players()
            except Exception as exc:
                error_state("Comparação indisponível", exc)
            return
    try:
        if pick == modes[1]:
            _match_vs_match()
            return
        if pick == modes[2]:
            _club_vs_club()
            return
        match_bar()
        ctx = current_context()
        if ctx is None:
            return
        if not ctx.has_events:
            empty_state("Este modo usa os eventos da partida aberta", "", "🆚", "Abra uma partida ✅ pelo 🔎 Buscar.")
            return
        {modes[0]: _players, modes[3]: _team_over_time, modes[4]: _two_teams}[pick](ctx)
        provenance_panel(ctx.registry)
    except Exception as exc:
        error_state("Comparação indisponível", exc)
