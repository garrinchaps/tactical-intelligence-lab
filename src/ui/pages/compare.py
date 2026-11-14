"""
Página Comparações:
  1. As duas equipes da partida lado a lado (indicadores, gols, destaques e redes de passes);
  2. Uma equipe comparada com ela mesma em outras partidas;
  3. Jogador × jogador — na partida aberta ou somando várias partidas de cada um (totais e por 90 min).
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from src.data_hub.gender import gender_of
from src.data_hub.search import team_score
from src.metrics.match_facts import (PLAYER_STAT_LABELS, TEAM_STAT_LABELS, goal_line, goals, per90, player_match_stats,
                                     team_match_stats)
from src.ui import charts
from src.ui.components import comparison_table, empty_state, error_state, kpi, note, page_header, provenance_panel
from src.ui.context import MatchContext, get_service, load_bundle, processed_events

MAX_MATCHES = 10
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
        st.plotly_chart(charts.grouped_bars(rows[~rows["indicador"].isin(["Passes", "Perdas de posse"])], "indicador", [a, b],
                                            "Indicadores das duas equipes", height=620), use_container_width=True)
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
            col.plotly_chart(charts.pass_network(net, f"{t} (até a 1ª substituição)"), use_container_width=True)
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
        st.plotly_chart(charts.grouped_bars(tab.melt(id_vars="partida", value_vars=pick).pivot(index="variable", columns="partida",
                                                                                            values="value").reset_index(),
                                            "variable", tab["partida"].tolist(), f"{team}: indicadores por partida",
                                            height=120 + 70 * len(pick)), use_container_width=True)
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
        st.plotly_chart(charts.radar({pa: [round(100 * float(p90a.iloc[0][c]) / mx[c], 1) for c in RADAR_KEYS],
                                      pb: [round(100 * float(p90b.iloc[0][c]) / mx[c], 1) for c in RADAR_KEYS]},
                                     [PLAYER_STAT_LABELS[c] for c in RADAR_KEYS],
                                     f"Por 90 min (100 = o maior dos dois) · {int(tot_a['minutos'])} e {int(tot_b['minutos'])} min"),
                        use_container_width=True)
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
