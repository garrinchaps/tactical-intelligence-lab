"""Página 1 — Match Center & Momento Tático (eventos) ou Boxscore Center."""

from __future__ import annotations

from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_hub.boxscore import STAT_LABELS
from src.machine_learning.clustering import SpatialTacticalClustering
from src.networks.pass_network import PassingNetworkAnalyzer
from src.reports.report_builder import BenchmarkDiscrepancyEngine
from src.tactical_engine.diagnostic_engine import TacticalDiagnosticEngine
from src.ui import charts
from src.ui.charts import _layout
from src.ui.components import (comparison_table, empty_state, error_state, metric_card, note, page_header, provenance_panel, scoreboard,
                               source_gap,
                               stat_pill)
from src.metrics.box_facts import box_facts
from src.ui.context import MatchContext
from src.ui.theme import PALETTE
from src.visualization.pitch_plots import TacticalVisualizer


def momentum_figure(df: pd.DataFrame, team_a: str, team_b: str) -> go.Figure:
    d = df[df["period"] <= 4].copy()
    d["bin"] = (d["minute"].fillna(0).astype(int) // 5) * 5
    bins = sorted(d["bin"].unique().tolist())
    vals = []
    for b in bins:
        w = d[d["bin"] == b]
        sc = []
        for t in (team_a, team_b):
            wt = w[w["team_name"] == t]
            sc.append(float(wt.get("delta_xt", pd.Series(0.0)).clip(lower=0).sum()) * 100
                      + float(wt["is_progressive_action"].sum()) * 1.5
                      + float(wt.get("shot_statsbomb_xg", pd.Series(0.0)).fillna(0).sum()) * 25)
        vals.append(round(sc[0] - sc[1], 2))
    fig = go.Figure(go.Bar(x=[f"{b}'" for b in bins], y=vals,
                           marker_color=[PALETTE["primary"] if v >= 0 else PALETTE["secondary"] for v in vals],
                           hovertext=[f"{b}'–{b + 5}': domínio de {team_a if v >= 0 else team_b} ({abs(v):.1f})"
                                      for b, v in zip(bins, vals)], hoverinfo="text"))
    fig.update_xaxes(title="minuto (janelas de 5 min)")
    fig.update_yaxes(title="índice de domínio (adimensional)")
    return _layout(fig, f"Momento da partida — verde: {team_a} · azul: {team_b}", 300)


def render_events(ctx: MatchContext) -> None:
    team, opp, df = ctx.target_team, ctx.opponent, ctx.df
    s, so = ctx.summary, ctx.opp_summary
    d_org, o_org, mid, d_tr = s["defensive_organization"], s["offensive_organization"], s["midfield_control"], s["defensive_transition"]
    opp_o, opp_d = so["offensive_organization"], so["defensive_organization"]
    aer_t = BenchmarkDiscrepancyEngine.extract_aerial_and_crossing_stats(df, team)
    aer_o = BenchmarkDiscrepancyEngine.extract_aerial_and_crossing_stats(df, opp)
    m = ctx.bundle.meta or {}
    from src.metrics.match_facts import goal_line, goals, shootout

    from src.ui.context import match_goals

    gl = match_goals(ctx.match_id, df)
    gt, go_ = sum(g["equipe"] == team for g in gl), sum(g["equipe"] == opp for g in gl)
    ctx.prov("placar", "Placar", f"{gt}-{go_}", "gols + gols contra nos eventos (sem disputa de pênaltis); "
             "assistência = último passe certo para o autor na mesma posse", raw=True)
    pen = shootout(df)
    scoreboard(team, opp, f"{gt} - {go_}", f"{m.get('competition_name', '')} {m.get('season_name', '')} · "
               f"{m.get('round_name', '') or ''} · {m.get('match_date', '')}",
               home_goals=[goal_line(g) for g in gl if g["equipe"] == team],
               away_goals=[goal_line(g) for g in gl if g["equipe"] == opp],
               extra_line=("Pênaltis: " + " x ".join(f"{t} {v}" for t, v in pen.items())) if pen else "")

    st.markdown("##### Indicadores-chave")
    from src.ui.glossary import what_is

    what_is(["xG", "xT", "PPDA", "Field Tilt"], key="mc_gloss")
    c = st.columns(6)
    with c[0]:
        metric_card("PPDA", d_org["ppda"], ctx.prov("ppda", "PPDA", d_org["ppda"],
                    "passes do adversário na construção (x ≤ 72) ÷ ações defensivas altas (x ≥ 48)", team=team, sim_key="ppda"),
                    "pressão alta" if d_org["ppda"] < 9 else d_org["block_profile"], "pos" if d_org["ppda"] < 9.5 else "neu",
                    unit="passes/ação")
    with c[1]:
        metric_card("Altura da linha", d_org["avg_defensive_engagement_height_m"],
                    ctx.prov("altura", "Altura da linha", d_org["avg_defensive_engagement_height_m"],
                             "média de x das ações defensivas, convertida para metros"),
                    f"± {d_org['longitudinal_dispersion_m']} m", "neu", unit="m")
    with c[2]:
        metric_card("Field Tilt", mid["field_tilt_pct"], ctx.prov("tilt", "Field Tilt", mid["field_tilt_pct"],
                    "participação nos passes no terço final", team=team, sim_key="field_tilt_pct"),
                    "domínio territorial" if mid["field_tilt_pct"] >= 52 else "bloco reativo",
                    "pos" if mid["field_tilt_pct"] >= 50 else "neg", unit="%")
    with c[3]:
        metric_card("Bolas na Zona 14", o_org["zone_14_entries"], ctx.prov("z14", "Zona 14", o_org["zone_14_entries"],
                    "ações que terminam na Zona 14"), f"{o_org['penalty_box_entries']} entradas na área", "neu", unit="ações")
    with c[4]:
        metric_card("Reação à perda (5 s)", d_tr["post_loss_5s_press_reaction_pct"],
                    ctx.prov("reacao", "Reação à perda", d_tr["post_loss_5s_press_reaction_pct"],
                             "% das perdas com ação defensiva em até 5 s"),
                    f"{d_tr['post_loss_5s_recoveries_count']} recuperações",
                    "pos" if d_tr["post_loss_5s_press_reaction_pct"] >= 45 else "neg", unit="%")
    with c[5]:
        metric_card("Duelos aéreos", aer_t["aerial_win_pct"], ctx.prov("aereo", "Duelos aéreos", aer_t["aerial_win_pct"],
                    "duelos aéreos ganhos ÷ disputados"), f"{aer_t['aerial_duels_won']}/{aer_t['aerial_duels_total']}", "neu", unit="%")

    left, right = st.columns([1.35, 1.0])
    with left:
        st.plotly_chart(momentum_figure(df, team, opp), use_container_width=True)
        ctx.prov("momento", "Momento da partida", "série", "Σ ΔxT positivo×100 + ações progressivas×1,5 + xG×25 por 5 min")
        try:
            st.plotly_chart(TacticalVisualizer.create_corridor_vulnerability_plotly(d_org, team), use_container_width=True)
        except Exception as exc:
            st.caption(f"Gráfico de corredores indisponível: {exc}")
    with right:
        st.markdown(f"##### {team} × {opp}")
        stat_pill("xG", o_org["total_xg"], opp_o["total_xg"], f"{o_org['total_xg']:.2f}", f"{opp_o['total_xg']:.2f}",
                  ctx.prov("xg", "xG", o_org["total_xg"], "soma do xG das finalizações (xG da fonte; Wyscout: modelo do laboratório)",
                           team=team, sim_key="total_xg"))
        stat_pill("Finalizações", o_org["total_shots"], opp_o["total_shots"], f"{o_org['total_shots']}", f"{opp_o['total_shots']}",
                  ctx.prov("shots", "Finalizações", o_org["total_shots"], "contagem de eventos de finalização", raw=True,
                           team=team, sim_key="total_shots"))
        stat_pill("Field Tilt", mid["field_tilt_pct"], 100 - mid["field_tilt_pct"], f"{mid['field_tilt_pct']:.1f}%",
                  f"{100 - mid['field_tilt_pct']:.1f}%", ctx.registry.get("tilt"))
        stat_pill("Passes (precisão)", o_org["total_passes"], opp_o["total_passes"],
                  f"{o_org['total_passes']} ({o_org['overall_pass_completion_pct']}%)",
                  f"{opp_o['total_passes']} ({opp_o['overall_pass_completion_pct']}%)",
                  ctx.prov("passes", "Passes", o_org["total_passes"], "passes e % de passes certos", team=team,
                           sim_key="overall_pass_completion_pct"))
        stat_pill("PPDA (menor = mais pressão)", d_org["ppda"], opp_d["ppda"], f"{d_org['ppda']}", f"{opp_d['ppda']}",
                  ctx.registry.get("ppda"), invert_advantage=True)
        stat_pill("Entradas na área", o_org["penalty_box_entries"], opp_o["penalty_box_entries"],
                  f"{o_org['penalty_box_entries']}", f"{opp_o['penalty_box_entries']}",
                  ctx.prov("area", "Entradas na área", o_org["penalty_box_entries"], "ações que terminam na grande área"))
        stat_pill("Duelos aéreos ganhos", aer_t["aerial_duels_won"], aer_o["aerial_duels_won"],
                  f"{aer_t['aerial_duels_won']}", f"{aer_o['aerial_duels_won']}", ctx.registry.get("aereo"))

    st.markdown("##### O que fugiu do padrão")
    try:
        disc = BenchmarkDiscrepancyEngine.generate_plain_language_discrepancy_conclusions(
            df_events=df, phases_metrics=s,
            passing_network=PassingNetworkAnalyzer.build_pass_network(df, team, until_first_sub=True)["graph_metrics"],
            clustering_data=SpatialTacticalClustering.analyze_turnover_clusters(df, team),
            target_team=team, opponent_team=opp)
        cols = st.columns(2)
        for i, text in enumerate(disc.get("plain_language_conclusions", [])):
            with cols[i % 2]:
                note("Discrepância contextual", text.replace("**", ""), "alert" if "🔴" in text else "")
    except Exception as exc:
        error_state("Conclusões indisponíveis", exc)

    st.markdown("##### Diagnósticos causa-efeito (Plano A e Plano B)")
    try:
        for d in TacticalDiagnosticEngine.generate_comprehensive_diagnostics(df, ctx.chains, team):
            with st.expander(f"[{d['evidence_strength']}] {d['problem_title']} — {d['pitch_zone']} (N = {d['sample_size']})"):
                st.markdown(f"**Diagnóstico:** {d['tactical_interpretation']}")
                a, b = st.columns(2)
                a.success(f"**Plano A:** {d['recommendation_plan_a']}")
                b.info(f"**Plano B:** {d['recommendation_alternative_b']}")
                st.caption(f"Risco: {d['recommendation_risks']} · Limitação: {d['data_limitations']}")
    except Exception as exc:
        error_state("Diagnósticos indisponíveis", exc)


def _understat_shots(ctx: MatchContext, home: str) -> None:
    """Mapa de finalizações e xG do Understat (baixado na hora, uma vez, se a partida estiver no Understat)."""
    try:
        from src.data_lake.understat_link import ensure_shots

        with st.spinner("Buscando as finalizações no Understat..."):
            shots = ensure_shots(ctx.match_id)
    except Exception:
        return False
    if shots is None or shots.empty:
        return False
    m = ctx.bundle.meta or {}
    shots = shots.assign(equipe=shots["lado"].map({"h": m.get("home_team_name", home), "a": m.get("away_team_name", "")})
                         .fillna(shots["equipe"]))                   # nomes iguais aos do placar
    st.markdown("##### 📍 Finalizações e xG (Understat)")
    by = shots.groupby("equipe").agg(chutes=("xg", "size"), xg=("xg", "sum"), gols=("resultado", lambda r: int((r == "gol").sum())))
    c = st.columns(len(by))
    for col, (team, r) in zip(c, by.iterrows()):
        with col:
            metric_card(f"xG — {team}", f"{r['xg']:.2f}",
                        ctx.prov(f"us_xg_{team}", f"xG {team}", round(float(r["xg"]), 2),
                                 "soma do xG das finalizações (modelo do Understat)", tier="DERIVED"),
                        f"{int(r['chutes'])} chutes · {int(r['gols'])} gols")
    st.plotly_chart(charts.shot_map(shots, m.get("home_team_name", home), "Finalizações (tamanho = xG, ★ = gol) — fonte: Understat"),
                    use_container_width=True)
    pl = (shots.groupby(["equipe", "jogador"]).agg(chutes=("xg", "size"), xg=("xg", "sum"),
                                                   gols=("resultado", lambda r: int((r == "gol").sum())))
          .reset_index().sort_values("xg", ascending=False))
    pl["xg"] = pl["xg"].round(2)
    a, b = st.columns(2)
    with a:
        st.markdown("###### Quem finalizou")
        comparison_table(pl.rename(columns={"equipe": "time"}))
    with b:
        st.markdown("###### Lance a lance")
        comparison_table(shots[["minuto", "equipe", "jogador", "assistente", "situacao", "tipo", "resultado", "xg"]]
                         .rename(columns={"equipe": "time", "situacao": "situação"}))
    return True


def _sibling_ids(ctx: MatchContext) -> List[int]:
    """A própria partida + a mesma partida em outras fontes (para buscar chutes/números por jogador da FotMob)."""
    ids = [int(ctx.match_id)]
    try:
        from src.data_hub.consolidate import siblings

        ids += [int(x["match_id"]) for x in siblings(ctx_db(ctx), ctx.match_id, ctx.bundle.meta) if int(x["match_id"]) not in ids]
    except Exception:
        pass
    return ids


SIT_PT = {"RegularPlay": "jogada", "FastBreak": "contra-ataque", "SetPiece": "bola parada", "FromCorner": "escanteio",
          "Penalty": "pênalti", "FreeKick": "falta direta", "ThrowInSetPiece": "lateral"}
OUT_PT = {"Goal": "gol", "AttemptSaved": "defendida", "Miss": "para fora", "Post": "trave", "Blocked": "bloqueada"}


def _fotmob_shots(ctx: MatchContext, home: str) -> None:
    """Mapa de finalizações e xG da FotMob (quando a partida, ou a mesma partida na FotMob, tem o mapa de chutes)."""
    try:
        ids = _sibling_ids(ctx)
        ph = ",".join("?" * len(ids))
        with ctx_db(ctx).connect() as conn:
            sh = pd.read_sql_query(f"SELECT * FROM match_shots WHERE match_id IN ({ph})", conn, params=ids)
    except Exception:
        return
    if sh.empty:
        return
    sh = sh[sh["match_id"] == sh["match_id"].iloc[0]]
    m = ctx.bundle.meta or {}
    from src.data_hub.service import _same
    from src.data_lake.ids import team_core

    hn = m.get("home_team_name", home)
    shots = pd.DataFrame({"lado": ["h" if _same(team_core(t), team_core(hn)) else "a" for t in sh["team_name"]],
                          "x": sh["x"], "y": sh["y"], "xg": pd.to_numeric(sh["xg"], errors="coerce").fillna(0),
                          "minuto": sh["minute"], "jogador": sh["player_name"],
                          "resultado": sh["outcome"].map(OUT_PT).fillna(sh["outcome"]),
                          "situacao": sh["situation"].map(SIT_PT).fillna(sh["situation"]), "tipo": sh["shot_type"]})
    shots["equipe"] = shots["lado"].map({"h": hn, "a": m.get("away_team_name", "")})
    st.markdown("##### 📍 Finalizações e xG (FotMob)")
    by = shots.groupby("equipe").agg(chutes=("xg", "size"), xg=("xg", "sum"), gols=("resultado", lambda r: int((r == "gol").sum())))
    for col, (team, r) in zip(st.columns(len(by)), by.iterrows()):
        with col:
            metric_card(f"xG — {team}", f"{r['xg']:.2f}",
                        ctx.prov(f"fm_xg_{team}", f"xG {team}", round(float(r["xg"]), 2),
                                 "soma do xG das finalizações (modelo da FotMob/Opta)", tier="DERIVED"),
                        f"{int(r['chutes'])} chutes · {int(r['gols'])} gols")
    st.plotly_chart(charts.shot_map(shots, hn, "Finalizações (tamanho = xG, ★ = gol) — fonte: FotMob"), use_container_width=True)


def _box_ratings(ctx: MatchContext) -> None:
    """Nota 2.0 por ESTATÍSTICAS (sem lances): régua própria, das atuações com números por jogador da mesma fonte."""
    from src.analytics import rating_box as RB

    for mid in _sibling_ids(ctx):
        r = _box_ratings_cached(int(mid))
        if r is not None and not r.empty:
            break
    else:
        return
    st.markdown("##### 🏅 Avaliação 2.0 dos jogadores (por estatísticas)")
    st.caption("Sem lances com coordenadas neste jogo: a nota usa os números por jogador (xG, xA, chances criadas, "
               "passes no terço final, desarmes, recuperações, duelos, perdas…) comparados com jogadores da MESMA função "
               "em outros jogos da mesma fonte. O que a fonte não mede (xT, pressão, entre linhas) não entra e reduz a "
               "confiança — nunca vira zero.")
    show = r.drop(columns=["_detalhe"]).rename(columns={"jogador": "Jogador", "equipe": "Time", "funcao": "Função",
                                                        "minutos": "Min", "gols": "Gols", "assistencias": "Assist.",
                                                        "desempenho": "Desempenho", "impacto": "Impacto",
                                                        "confianca": "Confiança", "confianca_pct": "Conf. %",
                                                        "classificacao": "Leitura", "pares": "Pares"})
    comparison_table(show)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=64)
def _box_ratings_cached(match_id: int):
    from src.analytics import rating_box as RB
    from src.ui.context import get_service

    try:
        return RB.match_ratings(get_service().db, match_id)
    except Exception:
        return None


def ctx_db(ctx):
    from src.ui.context import get_service

    return get_service().db


def _sources_panel(ctx: MatchContext) -> None:
    """A mesma partida em outras fontes: valor escolhido por precedência e divergências (nunca média)."""
    try:
        from src.data_hub.consolidate import compare
        from src.ui.context import get_service

        tab = compare(get_service().db, ctx.match_id, ctx.bundle.meta)
    except Exception:
        return
    if tab.empty:
        return
    try:                                              # B7: divergência registrada (nunca vira média)
        from src.data_hub.consolidate import record_divergences

        record_divergences(ctx_db(ctx), ctx.match_id, tab)
    except Exception:
        pass
    n_div = int(tab["diverge"].sum())
    srcs = sorted({x for x in tab["fonte escolhida"]} | {o.split(" ")[0] for v in tab["outras fontes"] if v != "—"
                                                        for o in v.split(", ")})
    with st.expander(f"🔀 Esta partida em {len(srcs)} fontes" + (f" · {n_div} número(s) divergem" if n_div else ""),
                     expanded=False):
        st.caption("Cada número vem da fonte de maior precedência para aquela estatística; quando outra fonte traz "
                   "um valor diferente, ele aparece ao lado — nada é somado nem tirado média.")
        comparison_table(tab.drop(columns=["stat_key", "side"]).assign(diverge=tab["diverge"].map({True: "⚠️ sim", False: ""})))


def _box_insights(ctx: MatchContext, stats: pd.DataFrame, team: str, opp: str) -> None:
    import html as _h

    m = ctx.bundle.meta or {}
    home = m.get("home_team_name")
    gf, ga = (m.get("home_score"), m.get("away_score")) if team == home else (m.get("away_score"), m.get("home_score"))
    good, bad = box_facts(stats, team, opp, gf, ga)
    if not good and not bad:
        return
    st.markdown(f"##### Leitura dos números — {team}")
    a, b = st.columns(2)
    for col, items, cls, title in ((a, good, "fm-card-blue", "✅ Pontos fortes"), (b, bad, "fm-card-red", "⚠️ Pontos fracos")):
        li = "".join(f"<li>{_h.escape(t)}</li>" for t, _, _ in items) or "<li>Nada que se destaque com clareza.</li>"
        col.markdown(f'<div class="fm-card {cls}"><div class="h">{title}</div><ul style="margin:.3rem 0 0 1rem">{li}</ul></div>',
                     unsafe_allow_html=True)
        for i, (t, val, how) in enumerate(items):
            ctx.prov(f"insight_{cls}_{i}", t.split(":")[0], val, how)


def render_boxscore(ctx: MatchContext) -> None:
    b, m = ctx.bundle, ctx.bundle.meta or {}
    home, away = m.get("home_team_name", ""), m.get("away_team_name", "")
    hs, as_ = m.get("home_score"), m.get("away_score")
    ctx.prov("placar", "Placar", f"{hs}-{as_}", "placar informado pela fonte", raw=True)
    tl = (b.boxscore or {}).get("timeline", pd.DataFrame())
    hg, ag = [], []
    if tl is not None and not tl.empty and "event_type" in tl.columns:
        for e in tl[tl["event_type"] == "Goal"].itertuples():
            extra = f"+{int(e.extra_minute)}" if pd.notna(e.extra_minute) and e.extra_minute else ""
            det = {"Penalty": " (pênalti)", "Own Goal": " (gol contra)"}.get(str(e.detail), "")
            line = f"{int(e.minute)}'{extra} {e.player_name}{det}" + (
                f" (assist. {e.related_player})" if isinstance(e.related_player, str) and e.related_player and not det else "")
            (hg if e.team_name == home else ag).append(line)
    scoreboard(home, away, f"{hs if hs is not None else '-'} - {as_ if as_ is not None else '-'}",
               f"{m.get('competition_name', '')} · {m.get('round_name', '')} · {m.get('match_date', '')} · {m.get('stadium_name', '')}",
               home_goals=hg, away_goals=ag)
    for n in b.notes:
        (st.info if ("trazidas" in n or "abrindo" in n) else st.warning)(n)
    if not _understat_shots(ctx, home):
        _fotmob_shots(ctx, home)
    _sources_panel(ctx)
    box = b.boxscore or {}
    stats, lineups, timeline, players = (box.get(k, pd.DataFrame()) for k in ("team_stats", "lineups", "timeline", "player_stats"))
    if stats.empty and lineups.empty and timeline.empty:
        source_gap("estatísticas de equipe", ctx.bundle.source,
                   "Ative a ESPN ou a API-Football no .env, ou escolha uma partida ✅ com eventos.", "📄", ctx.bundle.level)
        return
    if not stats.empty:
        _box_insights(ctx, stats, ctx.target_team or home, (away if (ctx.target_team or home) == home else home))
    left, right = st.columns(2)
    with left:
        st.markdown("##### Estatísticas da partida")
        for key, (label, higher) in STAT_LABELS.items():
            rows = stats[stats["stat_key"] == key] if not stats.empty else stats
            if rows.empty:
                continue
            hv = rows.loc[rows["team_name"] == home, "value"]
            av = rows.loc[rows["team_name"] == away, "value"]
            hv = float(hv.iloc[0]) if not hv.empty else None
            av = float(av.iloc[0]) if not av.empty else None
            fmt = lambda v: f"{v:g}" if v is not None else "—"
            stat_pill(label, hv, av, fmt(hv), fmt(av), ctx.prov(f"box_{key}", label, f"{fmt(hv)} x {fmt(av)}",
                      "estatística agregada informada pela fonte", raw=True), invert_advantage=not higher)
    with right:
        st.markdown("##### Linha do tempo")
        if timeline.empty:
            source_gap("lances (gols, cartões, substituições)", ctx.bundle.source, icon="⏱️")
        else:
            icon = {"goal": "⚽", "card": "🟨", "subst": "🔁", "var": "📺"}
            for r in timeline.itertuples():
                minute = f"{int(r.minute)}'" if pd.notna(r.minute) else ""
                if pd.notna(r.extra_minute) and r.extra_minute:
                    minute += f"+{int(r.extra_minute)}"
                ic = next((v for k, v in icon.items() if k in str(r.event_type).lower()), "•")
                extra = f" ({r.related_player})" if isinstance(r.related_player, str) and r.related_player.strip() else ""
                who = r.player_name if isinstance(r.player_name, str) and r.player_name.strip() else None
                team_txt = r.team_name if isinstance(r.team_name, str) and r.team_name.strip() else ""
                desc = str(r.detail or r.event_type).replace("Normal Goal", "Gol")
                # fonte sem autor/time (ex.: open-matchday): mostra só o que existe, sem asteriscos vazios
                st.markdown(f"`{minute:>6}` {ic} " + (f"**{who}**{extra} — " if who else "")
                            + (f"{team_txt} · " if team_txt else "") + desc
                            + ("" if who else " _(a fonte não informa o autor)_"))
    if not lineups.empty:
        st.markdown("##### Escalações")
        cols = st.columns(2)
        for i, t in enumerate([home, away]):
            lt = lineups[lineups["team_name"] == t]
            if lt.empty:
                continue
            form = lt["formation"].dropna().iloc[0] if lt["formation"].notna().any() else ""
            cols[i].markdown(f"**{t}** {('· ' + form) if form else ''}")
            cols[i].dataframe(lt[["shirt_number", "player_name", "position", "is_starter"]].rename(columns={
                "shirt_number": "Nº", "player_name": "Atleta", "position": "Posição", "is_starter": "Titular"}),
                use_container_width=True, hide_index=True)
    _box_ratings(ctx)


def render(ctx: MatchContext) -> None:
    page_header("🏟️ Match Center & Momento Tático", "Placar, indicadores-chave com origem declarada, momento do jogo e diagnósticos.", ctx)
    if ctx.is_sim and ctx.sim_ci:
        note("Partida simulada — intervalos de confiança do gerador",
             f"Gerador: {ctx.sim_ci['generator']}. Os IC 95% exibidos em cada métrica são a {ctx.sim_ci['ci_text']}: "
             "medem a incerteza do gerador, não a incerteza sobre um jogo real.", "warn")
    if ctx.has_events:
        render_events(ctx)
    else:
        render_boxscore(ctx)
    provenance_panel(ctx.registry)
