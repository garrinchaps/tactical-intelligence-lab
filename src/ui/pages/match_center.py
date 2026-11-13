"""Seção 🏟️ Partida — Match Center (eventos) ou Boxscore Center (estatísticas agregadas)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data_hub.boxscore import STAT_LABELS
from src.machine_learning.clustering import SpatialTacticalClustering
from src.networks.pass_network import PassingNetworkAnalyzer
from src.reports.report_builder import BenchmarkDiscrepancyEngine
from src.tactical_engine.diagnostic_engine import TacticalDiagnosticEngine
from src.ui.components import empty_state, metric_card, scoreboard, section_header, stat_pill
from src.ui.context import MatchContext
from src.visualization.pitch_plots import TacticalVisualizer


def momentum_figure(df: pd.DataFrame, team_a: str, team_b: str) -> go.Figure:
    d = df[df["period"] <= 4].copy()
    d["time_bin"] = (d["minute"].fillna(0).astype(int) // 5) * 5
    vals, colors, hover = [], [], []
    bins = sorted(d["time_bin"].unique().tolist())
    for b in bins:
        w = d[d["time_bin"] == b]
        score = []
        for t in (team_a, team_b):
            wt = w[w["team_name"] == t]
            score.append(float(wt.get("delta_xt", pd.Series(0.0)).clip(lower=0).sum()) * 100.0
                         + float(wt["is_progressive_action"].sum()) * 1.5
                         + float(wt.get("shot_statsbomb_xg", pd.Series(0.0)).fillna(0).sum()) * 25.0)
        net = round(score[0] - score[1], 2)
        vals.append(net)
        colors.append("#00FF7F" if net >= 0 else "#38BDF8")
        hover.append(f"Min {b}-{b + 5}: domínio de {team_a if net >= 0 else team_b} ({abs(net):.1f})")
    fig = go.Figure(go.Bar(x=[f"{b}'" for b in bins], y=vals, marker_color=colors, hovertext=hover, hoverinfo="text"))
    fig.update_layout(title=f"Momento da partida — verde: {team_a} · azul: {team_b}", template="plotly_dark",
                      paper_bgcolor="#1A1D24", plot_bgcolor="#1A1D24", height=290,
                      margin=dict(l=25, r=25, t=45, b=25), xaxis_title="Minuto (janelas de 5 min)",
                      yaxis_title="Índice de domínio (xT + xG)")
    return fig


def render_events(ctx: MatchContext) -> None:
    team, opp, df = ctx.target_team, ctx.opponent, ctx.df
    s, so = ctx.summary, ctx.opp_summary
    d_org, o_org, mid, d_tr = s["defensive_organization"], s["offensive_organization"], s["midfield_control"], s["defensive_transition"]
    opp_o, opp_d = so["offensive_organization"], so["defensive_organization"]
    aerial_t = BenchmarkDiscrepancyEngine.extract_aerial_and_crossing_stats(df, team)
    aerial_o = BenchmarkDiscrepancyEngine.extract_aerial_and_crossing_stats(df, opp)
    m = ctx.bundle.meta or {}

    scoreboard(team, opp, f"{ctx.goals(team)} - {ctx.goals(opp)}",
               subtitle_html=(f"xG: <b style='color:#00FF7F;'>{o_org['total_xg']:.2f}</b> vs "
                              f"<b style='color:#38BDF8;'>{opp_o['total_xg']:.2f}</b> &nbsp;|&nbsp; "
                              f"Bloco de {team}: <b>{d_org['block_profile']}</b> &nbsp;|&nbsp; "
                              f"{m.get('competition_name', '')} {m.get('season_name', '')}"))

    st.markdown("##### Indicadores-chave")
    c = st.columns(6)
    with c[0]:
        metric_card("PPDA", f"{d_org['ppda']}", "Pressão alta" if d_org["ppda"] < 9 else d_org["block_profile"],
                    "pos" if d_org["ppda"] < 9.5 else "neu")
    with c[1]:
        metric_card("Altura da linha", f"{d_org['avg_defensive_engagement_height_m']} m",
                    f"± {d_org['longitudinal_dispersion_m']} m",
                    "pos" if d_org["avg_defensive_engagement_height_m"] >= 42 else "neu")
    with c[2]:
        metric_card("Field Tilt", f"{mid['field_tilt_pct']}%",
                    "Domínio territorial" if mid["field_tilt_pct"] >= 52 else "Bloco reativo",
                    "pos" if mid["field_tilt_pct"] >= 50 else "neg")
    with c[3]:
        metric_card("Zona 14", f"{o_org['zone_14_entries']}", f"{o_org['penalty_box_entries']} entradas na área",
                    "pos" if o_org["zone_14_entries"] >= 8 else "neu")
    with c[4]:
        metric_card("Reação à perda (5 s)", f"{d_tr['post_loss_5s_press_reaction_pct']}%",
                    f"{d_tr['post_loss_5s_recoveries_count']} recuperações",
                    "pos" if d_tr["post_loss_5s_press_reaction_pct"] >= 45 else "neg")
    with c[5]:
        metric_card("Duelos aéreos", f"{aerial_t['aerial_win_pct']}%",
                    f"{aerial_t['aerial_duels_won']}/{aerial_t['aerial_duels_total']} ganhos",
                    "pos" if aerial_t["aerial_win_pct"] >= 52 else "neu")

    left, right = st.columns([1.35, 1.0])
    with left:
        st.plotly_chart(momentum_figure(df, team, opp), use_container_width=True)
        try:
            st.plotly_chart(TacticalVisualizer.create_corridor_vulnerability_plotly(d_org, team),
                            use_container_width=True)
        except Exception as exc:
            st.caption(f"Gráfico de corredores indisponível: {exc}")
    with right:
        st.markdown(f"##### Comparativo — <span style='color:#00FF7F'>{team}</span> x "
                    f"<span style='color:#38BDF8'>{opp}</span>", unsafe_allow_html=True)
        stat_pill("xG", o_org["total_xg"], opp_o["total_xg"], f"{o_org['total_xg']:.2f}", f"{opp_o['total_xg']:.2f}")
        stat_pill("Finalizações", o_org["total_shots"], opp_o["total_shots"], f"{o_org['total_shots']}", f"{opp_o['total_shots']}")
        stat_pill("Field Tilt", mid["field_tilt_pct"], 100 - mid["field_tilt_pct"], f"{mid['field_tilt_pct']:.1f}%",
                  f"{100 - mid['field_tilt_pct']:.1f}%")
        stat_pill("Passes (precisão)", o_org["total_passes"], opp_o["total_passes"],
                  f"{o_org['total_passes']} ({o_org['overall_pass_completion_pct']}%)",
                  f"{opp_o['total_passes']} ({opp_o['overall_pass_completion_pct']}%)")
        stat_pill("PPDA (menor = mais pressão)", d_org["ppda"], opp_d["ppda"], f"{d_org['ppda']}",
                  f"{opp_d['ppda']}", invert_advantage=True)
        stat_pill("Entradas na área", o_org["penalty_box_entries"], opp_o["penalty_box_entries"],
                  f"{o_org['penalty_box_entries']}", f"{opp_o['penalty_box_entries']}")
        stat_pill("Duelos aéreos ganhos", aerial_t["aerial_duels_won"], aerial_o["aerial_duels_won"],
                  f"{aerial_t['aerial_duels_won']}", f"{aerial_o['aerial_duels_won']}")

    st.markdown("##### O que fugiu do padrão")
    try:
        disc = BenchmarkDiscrepancyEngine.generate_plain_language_discrepancy_conclusions(
            df_events=df, phases_metrics=s,
            passing_network=PassingNetworkAnalyzer.build_pass_network(df, team, until_first_sub=True)["graph_metrics"],
            clustering_data=SpatialTacticalClustering.analyze_turnover_clusters(df, team),
            target_team=team, opponent_team=opp)
        cols = st.columns(2)
        for i, conclusion in enumerate(disc.get("plain_language_conclusions", [])):
            style = "til-card-alert" if "🔴" in conclusion else "til-card-neon"
            cols[i % 2].markdown(f'<div class="{style}" style="font-size:0.88rem;">{conclusion}</div>',
                                 unsafe_allow_html=True)
    except Exception as exc:
        st.caption(f"Conclusões indisponíveis: {exc}")

    st.markdown("##### Diagnósticos causa-efeito (Plano A e Plano B)")
    try:
        for d in TacticalDiagnosticEngine.generate_comprehensive_diagnostics(df, ctx.chains, team):
            with st.expander(f"[{d['evidence_strength']}] {d['problem_title']} — {d['pitch_zone']} (N={d['sample_size']})"):
                st.markdown(f"**Diagnóstico:** {d['tactical_interpretation']}")
                a, b = st.columns(2)
                a.success(f"**Plano A:** {d['recommendation_plan_a']}")
                b.info(f"**Plano B:** {d['recommendation_alternative_b']}")
                st.caption(f"Risco: {d['recommendation_risks']} | Limitação: {d['data_limitations']}")
    except Exception as exc:
        st.caption(f"Diagnósticos indisponíveis: {exc}")


def render_boxscore(ctx: MatchContext) -> None:
    b, m = ctx.bundle, ctx.bundle.meta or {}
    home, away = m.get("home_team_name", ""), m.get("away_team_name", "")
    hs, as_ = m.get("home_score"), m.get("away_score")
    scoreboard(home, away, f"{hs if hs is not None else '-'} - {as_ if as_ is not None else '-'}",
               subtitle_html=f"{m.get('competition_name', '')} · {m.get('round_name', '')} · {m.get('match_date', '')}"
                             f" · {m.get('stadium_name', '')}")
    for n in b.notes:
        st.warning(n)
    box = b.boxscore or {}
    stats, lineups, timeline, players = (box.get(k, pd.DataFrame()) for k in
                                         ("team_stats", "lineups", "timeline", "player_stats"))
    if stats.empty and lineups.empty and timeline.empty:
        empty_state("Esta fonte só traz o placar desta partida. Para estatísticas, habilite a API-Football "
                    "ou o feed ESPN no .env, ou escolha uma partida com eventos (✅).")
        return

    left, right = st.columns([1.0, 1.0])
    with left:
        st.markdown("##### Estatísticas da partida")
        if stats.empty:
            st.caption("Sem estatísticas agregadas nesta fonte.")
        for key in STAT_LABELS:
            rows = stats[stats["stat_key"] == key]
            if rows.empty:
                continue
            hv = rows.loc[rows["team_name"] == home, "value"]
            av = rows.loc[rows["team_name"] == away, "value"]
            hv = float(hv.iloc[0]) if not hv.empty else None
            av = float(av.iloc[0]) if not av.empty else None
            fmt = (lambda v: f"{v:g}" if v is not None else "—")
            stat_pill(STAT_LABELS[key][0], hv, av, fmt(hv), fmt(av), invert_advantage=not STAT_LABELS[key][1])
    with right:
        st.markdown("##### Linha do tempo")
        if timeline.empty:
            st.caption("Sem lances registrados.")
        else:
            icon = {"Goal": "⚽", "Card": "🟨", "subst": "🔁", "Var": "📺"}
            for r in timeline.itertuples():
                minute = f"{int(r.minute)}'" if pd.notna(r.minute) else ""
                if pd.notna(r.extra_minute) and r.extra_minute:
                    minute += f"+{int(r.extra_minute)}"
                ic = next((v for k, v in icon.items() if k.lower() in str(r.event_type).lower()), "•")
                extra = f" ({r.related_player})" if r.related_player else ""
                st.markdown(f"`{minute:>6}` {ic} **{r.player_name}**{extra} — {r.team_name} · {r.detail or r.event_type}")

    if not lineups.empty:
        st.markdown("##### Escalações")
        cols = st.columns(2)
        for i, t in enumerate([home, away]):
            lt = lineups[lineups["team_name"] == t]
            if lt.empty:
                continue
            form = lt["formation"].dropna().iloc[0] if lt["formation"].notna().any() else ""
            coach = lt["coach"].dropna().iloc[0] if lt["coach"].notna().any() else ""
            cols[i].markdown(f"**{t}** {('· ' + form) if form else ''} {('· técnico: ' + coach) if coach else ''}")
            cols[i].dataframe(lt[["shirt_number", "player_name", "position", "is_starter"]].rename(columns={
                "shirt_number": "Nº", "player_name": "Atleta", "position": "Pos.", "is_starter": "Titular"}),
                use_container_width=True, hide_index=True)
    if players is not None and not players.empty:
        st.markdown("##### Atletas (estatísticas individuais da fonte)")
        flat = players.drop(columns=["stats_json", "match_id"], errors="ignore").copy()
        extra = pd.json_normalize(flat.pop("stats")) if "stats" in flat else pd.DataFrame()
        st.dataframe(pd.concat([flat.reset_index(drop=True), extra], axis=1)
                     .sort_values("rating", ascending=False, na_position="last"),
                     use_container_width=True, hide_index=True)


def render(ctx: MatchContext) -> None:
    section_header("🏟️ Partida", "Placar, indicadores-chave, momento do jogo e diagnósticos.")
    if ctx.has_events:
        render_events(ctx)
    else:
        render_boxscore(ctx)
