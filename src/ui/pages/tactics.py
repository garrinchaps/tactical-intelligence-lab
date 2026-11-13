"""Seção 🧭 Tática — redes de passes, xT, clusters e modelo de perigo de posse."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from src.ingestion.brazil_and_multi_source import PlayerNameNormalizer
from src.machine_learning.clustering import SpatialTacticalClustering
from src.machine_learning.supervised import PossessionDangerClassifier
from src.metrics.xt_model import ExpectedThreatModel
from src.networks.pass_network import PassingNetworkAnalyzer
from src.ui.components import empty_state, metric_card, section_header
from src.ui.context import MatchContext
from src.visualization.pitch_plots import TacticalVisualizer


def _networks(ctx: MatchContext) -> None:
    team, df = ctx.target_team, ctx.df
    until_sub = st.checkbox("Rede até a 1ª substituição (estrutura dos 11 titulares)", value=True)
    net = PassingNetworkAnalyzer.build_pass_network(df, team, until_first_sub=until_sub, min_pass_count=2)
    gm = net["graph_metrics"]
    xt = ExpectedThreatModel.compute_team_xt_summary(df, team)
    c = st.columns(4)
    with c[0]:
        metric_card("Estrutura em posse", str(gm.get("inferred_positional_structure", "—")),
                    f"até {gm.get('analyzed_until_minute', 90)}'", "pos")
    with c[1]:
        metric_card("Pivô (betweenness)",
                    PlayerNameNormalizer.to_common_name(str(gm.get("primary_bridge_player_betweenness", "—"))),
                    f"score {gm.get('primary_bridge_score', 0)}", "pos")
    with c[2]:
        metric_card("Centro gravitacional (PageRank)",
                    PlayerNameNormalizer.to_common_name(str(gm.get("primary_gravity_playmaker_pagerank", "—"))),
                    f"share máx. {gm.get('max_player_pass_share_pct', 0)}%", "neu")
    with c[3]:
        metric_card("xT gerado", f"+{xt.get('total_xt_generated', 0.0):.3f}",
                    f"densidade {gm.get('network_density', 0)}", "pos")
    a, b = st.columns(2)
    with a:
        fig = TacticalVisualizer.plot_passing_network(net)
        st.pyplot(fig)
        plt.close(fig)
    with b:
        fig = TacticalVisualizer.plot_progression_and_xt_map(df, team)
        st.pyplot(fig)
        plt.close(fig)
    if not net["nodes_df"].empty:
        with st.expander("Matriz de centralidades (NetworkX)"):
            cols = [c for c in ["player_name", "position_name", "avg_x", "avg_y", "passes_made", "passes_received",
                                "progressive_passes_made", "betweenness_centrality", "pagerank_centrality",
                                "clustering_coeff"] if c in net["nodes_df"].columns]
            st.dataframe(net["nodes_df"][cols], use_container_width=True, hide_index=True)


def _ml(ctx: MatchContext) -> None:
    team, df = ctx.target_team, ctx.df
    km = SpatialTacticalClustering.analyze_turnover_clusters(df, team)
    db = SpatialTacticalClustering.analyze_recovery_density_dbscan(df, team)
    a, b = st.columns([1.15, 1.0])
    with a:
        fig = TacticalVisualizer.plot_spatial_clusters_and_press_traps(
            df, {"kmeans_turnovers": km, "dbscan_recoveries": db}, team)
        st.pyplot(fig)
        plt.close(fig)
    with b:
        risk = km.get("highest_risk_exposure_cluster") or {}
        st.markdown(
            f"""<div class="til-card-alert"><div class="metric-label">Zona de maior risco de perda (K-Means)</div>
            <div style="font-size:1.2rem; font-weight:800; color:#FF4B4B;">{risk.get('tactical_third', '—')} • {risk.get('tactical_corridor', '—')}</div>
            <div style="font-size:0.86rem; color:#E2E8F0; margin-top:6px;">Perda por toque: <b>{risk.get('turnover_rate_per_touch_pct', 0)}%</b>
            ({risk.get('local_radius_turnovers_numerator', 0)} perdas em {risk.get('local_radius_touches_denominator', 0)} toques) ·
            K = {km.get('optimal_k', 0)} (silhouette {km.get('silhouette_score', 0)})</div></div>""",
            unsafe_allow_html=True)
        if km.get("clusters"):
            st.dataframe(pd.DataFrame(km["clusters"]), use_container_width=True, hide_index=True)

    st.markdown("##### Perigo de posse (XGBoost)")
    clf = PossessionDangerClassifier()
    trained = clf.load_models()
    if st.button("Treinar/recalibrar o modelo nesta partida"):
        with st.spinner("Treinando XGBoost e regressão logística..."):
            clf.train_and_evaluate(ctx.chains)
            trained = True
    if trained and clf.xgb_model is not None:
        mx = clf.latest_metrics.get("xgboost_metrics", {})
        c = st.columns(3)
        with c[0]:
            metric_card("ROC-AUC (teste)", f"{mx.get('test_roc_auc', 0)}", "poder discriminante", "pos")
        with c[1]:
            metric_card("F1", f"{mx.get('test_f1_score', 0)}", f"precisão {mx.get('test_precision', 0)}", "neu")
        with c[2]:
            metric_card("Brier", f"{mx.get('test_brier_score', 0)}", "calibração", "neu")
        try:
            pred = clf.predict_possession_probabilities(ctx.chains, target_team=team)
            if pred.get("status") == "OK":
                st.markdown(f"Corredor inicial com maior perigo esperado: **{pred['highest_probability_start_corridor']}** "
                            f"(previsto {pred['avg_predicted_danger_prob_pct']}% · real {pred['actual_danger_rate_pct']}%)")
                st.dataframe(pd.DataFrame(pred["corridor_probabilities"]).T, use_container_width=True)
        except Exception as exc:
            st.caption(f"Previsão indisponível: {exc}")
    else:
        st.caption("Modelo ainda não treinado: use o botão acima.")


def render(ctx: MatchContext) -> None:
    section_header("🧭 Tática", f"Como {ctx.target_team} circulou a bola, gerou ameaça e onde perdeu a posse.")
    if not ctx.has_events:
        empty_state("Esta partida só tem boxscore: redes de passes, xT e clusters precisam de eventos com "
                    "coordenadas. Escolha uma partida ✅ (StatsBomb ou Wyscout).")
        return
    t1, t2 = st.tabs(["🕸️ Redes de passes & xT", "🤖 Perdas, recuperações & perigo de posse"])
    with t1:
        try:
            _networks(ctx)
        except Exception as exc:
            st.warning(f"Rede de passes indisponível: {exc}")
    with t2:
        try:
            _ml(ctx)
        except Exception as exc:
            st.warning(f"Módulo de machine learning indisponível: {exc}")
