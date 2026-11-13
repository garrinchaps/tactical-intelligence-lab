"""Seção 👤 Jogadores — elenco e substituições, scout individual e pontos fortes/fracos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.reports.report_builder import TacticalReportBuilder
from src.ui.components import empty_state, section_header
from src.ui.context import MatchContext, get_service
from src.visualization.pitch_plots import TacticalVisualizer
from src.visualization.strengths_page import render_strengths_weaknesses_page

SECTORS = [
    ("Goleiro & defesa", ["Goalkeeper", "Back"]),
    ("Volantes & construção", ["Defensive Midfield", "Center Midfield"]),
    ("Meias & extremos", ["Attacking Midfield", "Wing", "Left Midfield", "Right Midfield"]),
    ("Ataque", ["Forward", "Striker"]),
]


def _squad(ctx: MatchContext, players_df: pd.DataFrame) -> None:
    st.markdown("##### Matriz de profundidade por setor")
    cols = st.columns(4)
    for i, (title, kws) in enumerate(SECTORS):
        with cols[i]:
            st.markdown(f'<div class="depth-slot"><div class="depth-role-title">{title}</div>', unsafe_allow_html=True)
            sec = players_df[players_df["position_name"].apply(lambda p: any(k.lower() in str(p).lower() for k in kws))]
            if sec.empty:
                st.caption("Sem atletas neste setor.")
            for _, p in sec.head(5).iterrows():
                st.markdown(f"**{p['player_name']}** `{p['estimated_minutes_active']}'`  \n"
                            f"<span style='color:#00FF7F;font-size:0.8rem;'>score {p['tactical_impact_score']}</span> · "
                            f"<span style='color:#94A3B8;font-size:0.8rem;'>xT +{p['xt_generated']:.3f} · passe {p['pass_accuracy_pct']}%</span>",
                            unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("##### Substituições sugeridas (queda após o minuto 60)")
    subs = PlayerTacticalEvaluator.recommend_tactical_substitutions(ctx.df, ctx.target_team)
    if subs["recommended_substitutions"]:
        for rec in subs["recommended_substitutions"]:
            st.markdown(
                f"""<div class="til-card-alert"><div style="font-weight:800; color:#FF4B4B;">⚠️ {rec['candidate_out']}
                ({rec['position']}) — prioridade {rec['priority_score']}</div>
                <p style="font-size:0.86rem; margin:6px 0;"><b>Evidência:</b> {' '.join(rec['tactical_reasons'])}</p>
                <p style="font-size:0.86rem; margin:6px 0; color:#00FF7F;"><b>Perfil para entrar:</b> {rec['ideal_replacement_profile']}</p>
                <p style="font-size:0.78rem; color:#94A3B8; margin:0;"><b>Risco:</b> {' '.join(rec['structural_risks_of_substitution'])}</p></div>""",
                unsafe_allow_html=True)
    else:
        st.success("Nenhum titular teve queda técnica crítica após o minuto 60.")
    st.caption(subs["data_limitations_notice"])
    with st.expander("Tabela completa de desempenho individual"):
        st.dataframe(players_df, use_container_width=True, hide_index=True)


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
    st.markdown("##### Comparador direto (radar)")
    if len(players_df) >= 2:
        names = players_df["player_name"].tolist()
        c1, c2 = st.columns(2)
        pa = c1.selectbox("Atleta A", names, index=0)
        pb = c2.selectbox("Atleta B", names, index=1)
        st.plotly_chart(TacticalVisualizer.create_player_comparison_radar_plotly(players_df, pa, pb),
                        use_container_width=True)


def render(ctx: MatchContext) -> None:
    section_header("👤 Jogadores", f"Elenco de {ctx.target_team}, scout individual e comparação com a elite da função.")
    if not ctx.has_events:
        players = ctx.bundle.boxscore.get("player_stats") if ctx.bundle.boxscore else None
        if players is not None and not players.empty:
            st.markdown("Esta partida tem estatísticas individuais da fonte (sem coordenadas):")
            flat = players.drop(columns=["stats_json", "match_id"], errors="ignore").copy()
            extra = pd.json_normalize(flat.pop("stats")) if "stats" in flat else pd.DataFrame()
            st.dataframe(pd.concat([flat.reset_index(drop=True), extra], axis=1), use_container_width=True, hide_index=True)
        else:
            empty_state("Sem dados individuais nesta fonte. Escolha uma partida ✅ para scout completo.")
        return
    players_df = PlayerTacticalEvaluator.evaluate_team_players(ctx.df, ctx.target_team)
    t1, t2, t3 = st.tabs(["🧩 Elenco & substituições", "🕵️ Scout & comparador", "⚖️ Pontos fortes e fracos"])
    with t1:
        try:
            _squad(ctx, players_df)
        except Exception as exc:
            st.warning(f"Elenco indisponível: {exc}")
    with t2:
        try:
            _scout(ctx, players_df)
        except Exception as exc:
            st.warning(f"Scout indisponível: {exc}")
    with t3:
        render_strengths_weaknesses_page(
            df_events=ctx.df, df_chains=ctx.chains, target_team=ctx.target_team,
            current_match_id=ctx.match_id, is_sim_mode=ctx.is_sim,
            load_events_fn=get_service().db.load_events,
        )
