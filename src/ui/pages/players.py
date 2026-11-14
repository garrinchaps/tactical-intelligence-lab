"""Página 5 — Jogadores: elenco por setor, substituições sugeridas, dossiê e comparador (radar com n)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.reports.report_builder import TacticalReportBuilder
from src.ui.components import comparison_table, empty_state, error_state, note, page_header, provenance_panel
from src.ui.context import MatchContext
from src.ui.theme import PALETTE, PLOTLY_LAYOUT

SECTORS = [
    ("Goleiro & defesa", ["Goalkeeper", "Back"]),
    ("Volantes & construção", ["Defensive Midfield", "Center Midfield"]),
    ("Meias & extremos", ["Attacking Midfield", "Wing", "Left Midfield", "Right Midfield"]),
    ("Ataque", ["Forward", "Striker"]),
]
RADAR = [("passes_completed", "Passes completos"), ("press_retention_pct", "Retenção sob pressão (%)"),
         ("progressive_actions", "Ações progressivas"), ("line_breaking_passes", "Passes quebra-linhas"),
         ("xt_generated", "xT gerado"), ("ball_recoveries", "Recuperações")]
MIN_RADAR_MINUTES = 20


def _squad(ctx: MatchContext, players_df: pd.DataFrame) -> None:
    ctx.prov("elenco", "Desempenho individual", len(players_df), "PlayerTacticalEvaluator sobre os eventos da partida")
    st.markdown("#### Matriz de profundidade por setor")
    cols = st.columns(4)
    for i, (title, kws) in enumerate(SECTORS):
        sec = players_df[players_df["position_name"].apply(lambda p: any(k.lower() in str(p).lower() for k in kws))]
        rows = "".join(f'<div class="p"><b>{p.player_name}</b> <span class="m">{p.estimated_minutes_active}\'</span><br>'
                       f'<span class="m">xT +{p.xt_generated:.3f} · passe {p.pass_accuracy_pct}% · score {p.tactical_impact_score}</span></div>'
                       for p in sec.head(5).itertuples()) or '<div class="m">Sem atletas neste setor.</div>'
        cols[i].markdown(f'<div class="til-depth"><div class="h">{title}</div>{rows}</div>', unsafe_allow_html=True)

    st.markdown("#### Substituições sugeridas (queda após o minuto 60)")
    subs = PlayerTacticalEvaluator.recommend_tactical_substitutions(ctx.df, ctx.target_team)
    if subs["recommended_substitutions"]:
        for rec in subs["recommended_substitutions"]:
            note(f"⚠️ {rec['candidate_out']} ({rec['position']}) — prioridade {rec['priority_score']}",
                 f"Evidência: {' '.join(rec['tactical_reasons'])} · Perfil para entrar: {rec['ideal_replacement_profile']} · "
                 f"Risco: {' '.join(rec['structural_risks_of_substitution'])}", "warn")
    else:
        note("Sem queda crítica", "Nenhum titular teve queda técnica crítica após o minuto 60.")
    st.caption(subs["data_limitations_notice"])
    with st.expander("Tabela completa de desempenho individual"):
        comparison_table(players_df)


def _radar(players_df: pd.DataFrame, a: str, b: str) -> go.Figure:
    """Normaliza pelo máximo da equipe NA PARTIDA; o n (atletas com ≥ 20 min) aparece no título."""
    pool = players_df[players_df["estimated_minutes_active"] >= MIN_RADAR_MINUTES]
    fig = go.Figure()
    n = len(pool)
    if n < 3:
        fig.add_annotation(text=f"amostra insuficiente (n = {n} atletas com ≥ {MIN_RADAR_MINUTES} min)", showarrow=False,
                           font=dict(color=PALETTE["warning"]))
    else:
        mx = {c: max(float(pool[c].max()), 1e-4) for c, _ in RADAR}
        labels = [l for _, l in RADAR]
        for name, color in ((a, PALETTE["secondary"]), (b, PALETTE["warning"])):
            row = players_df[players_df["player_name"] == name]
            if row.empty:
                continue
            r = row.iloc[0]
            vals = [round(100 * float(r[c]) / mx[c], 1) for c, _ in RADAR]
            fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1], fill="toself",
                                          name=f"{name} ({r['estimated_minutes_active']}')", line=dict(color=color)))
    fig.update_layout(**PLOTLY_LAYOUT, height=460,
                      title=f"% do máximo da equipe nesta partida · n = {n} atletas com ≥ {MIN_RADAR_MINUTES} min",
                      polar=dict(bgcolor=PALETTE["surface"], radialaxis=dict(range=[0, 100], color=PALETTE["muted"])))
    return fig


def _scout(ctx: MatchContext, players_df: pd.DataFrame) -> None:
    a, b = st.columns([2.2, 1.0])
    player = a.selectbox("Atleta (qualquer equipe)", ctx.players)
    b.write("")
    if b.button("Gerar dossiê do atleta", type="primary", use_container_width=True) and player:
        md = TacticalReportBuilder.prepend_simulation_badge(
            TacticalReportBuilder.build_dedicated_player_scouting_report(ctx.df, player), ctx.is_sim)
        st.markdown(md)
        st.download_button(f"Baixar dossiê de {player} (.md)", data=md,
                           file_name=f"scout_{player.lower().replace(' ', '_')}.md", mime="text/markdown")
    st.markdown("#### Comparador direto (radar)")
    if len(players_df) >= 2:
        names = players_df["player_name"].tolist()
        c1, c2 = st.columns(2)
        pa = c1.selectbox("Atleta A", names, index=0)
        pb = c2.selectbox("Atleta B", names, index=1)
        ctx.prov("radar", "Radar comparativo", f"{pa} x {pb}", "percentual do máximo da equipe na partida")
        st.plotly_chart(_radar(players_df, pa, pb), use_container_width=True)
        if ctx.is_sim:
            note("Partida simulada", "Os valores individuais vêm do gerador por perfis: comparação ilustrativa.", "warn")


def _stats_table(ctx: MatchContext) -> None:
    from src.metrics.match_facts import PLAYER_STAT_LABELS, per90, player_match_stats

    a, b = st.columns([1.4, 1])
    who = a.radio("Atletas de", [ctx.target_team, ctx.opponent, "Ambas as equipes"], horizontal=True, key="ps_team")
    mode = b.radio("Valores", ["Totais", "Por 90 minutos"], horizontal=True, key="ps_mode")
    s = player_match_stats(ctx.df, None if who == "Ambas as equipes" else who)
    if s.empty:
        empty_state("Sem atletas com eventos.")
        return
    ctx.prov("ps_table", "Estatísticas individuais", len(s), "contagem de eventos por atleta; minutos estimados pelas substituições")
    if mode == "Por 90 minutos":
        s = per90(s)
        note("Por 90 minutos", "Atletas com poucos minutos têm valores por 90 instáveis: veja a coluna de minutos.", "warn")
    order = st.selectbox("Ordenar por", list(PLAYER_STAT_LABELS), index=list(PLAYER_STAT_LABELS).index("xt"),
                         format_func=lambda k: PLAYER_STAT_LABELS[k], key="ps_order")
    s = s.sort_values(order, ascending=False)
    comparison_table(s.rename(columns={"jogador": "Jogador", "equipe": "Equipe", "posicao": "Posição", **PLAYER_STAT_LABELS}),
                     "Contagens diretas dos eventos da partida. Assistência = último passe certo para o autor do gol.")
    st.download_button("Baixar tabela (.csv)", s.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"atletas_{ctx.match_id}.csv", mime="text/csv")


def render(ctx: MatchContext) -> None:
    page_header("👤 Jogadores", f"Elenco de {ctx.target_team}, substituições, dossiê individual e comparador.", ctx)
    if not ctx.has_events:
        ps = ctx.bundle.boxscore.get("player_stats") if ctx.bundle.boxscore else None
        if ps is not None and not ps.empty:
            ctx.prov("ps", "Estatísticas individuais", len(ps), "lidas da fonte", raw=True)
            st.markdown("Estatísticas individuais da fonte (sem coordenadas):")
            flat = ps.drop(columns=["stats_json", "match_id"], errors="ignore").copy()
            extra = pd.json_normalize(flat.pop("stats")) if "stats" in flat else pd.DataFrame()
            comparison_table(pd.concat([flat.reset_index(drop=True), extra], axis=1))
            provenance_panel(ctx.registry)
        else:
            empty_state("Sem dados individuais nesta fonte", "", "👤", "Escolha uma partida ✅ (eventos) para o scout completo.")
        return
    players_df = PlayerTacticalEvaluator.evaluate_team_players(ctx.df, ctx.target_team)
    t0, t1, t2 = st.tabs(["📋 Estatísticas individuais", "🧩 Elenco & substituições", "🕵️ Dossiê & comparador"])
    with t0:
        try:
            _stats_table(ctx)
        except Exception as exc:
            error_state("Estatísticas indisponíveis", exc)
    with t1:
        try:
            _squad(ctx, players_df)
        except Exception as exc:
            error_state("Elenco indisponível", exc)
    with t2:
        try:
            _scout(ctx, players_df)
        except Exception as exc:
            error_state("Scout indisponível", exc)
    provenance_panel(ctx.registry)
