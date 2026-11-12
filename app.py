"""
TACTICAL INTELLIGENCE LAB — Aplicação Web Principal (Streamlit)
Design System Dark Mode (Sofascore / Football Manager Data Hub / DataMB / CIES / Simonetti Análises)
Integrando IA Generativa (Gemini), Classificação Neural MLP e Auditoria Anti-Alucinação.
Preserva 100% dos motores analíticos, grafos, xT, Machine Learning e a suíte de 24 testes pytest.
Execução: streamlit run app.py
"""

import os
from pathlib import Path
from typing import Any, Dict, Tuple
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ingestion.statsbomb_loader import StatsBombDataLoader
from src.ingestion.brazil_and_multi_source import PlayerNameNormalizer
from src.preprocessing.event_cleaner import EventPreprocessor
from src.metrics.tactical_metrics import TacticalMetricsEngine
from src.networks.pass_network import PassingNetworkAnalyzer
from src.metrics.xt_model import ExpectedThreatModel
from src.machine_learning.clustering import SpatialTacticalClustering
from src.machine_learning.supervised import PossessionDangerClassifier
from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.metrics.multi_match_analyzer import MultiMatchTrendAnalyzer
from src.tactical_engine.diagnostic_engine import TacticalDiagnosticEngine
from src.reports.report_builder import (
    TacticalReportBuilder,
    NumericHallucinationGuard,
    BenchmarkDiscrepancyEngine,
)
from src.intelligence.llm_analyst import GenerativeTacticalAnalyst
from src.visualization.pitch_plots import TacticalVisualizer
from src.ingestion.video_homography_demo import PitchHomographyProjector

st.set_page_config(
    page_title="Tactical Intelligence Lab | Elite Football Analytics",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# 1. DESIGN SYSTEM & CSS CUSTOMIZADO (SOFASCORE / FM DATA HUB / DATAMB)
# =============================================================================
def inject_elite_design_system() -> None:
    st.markdown(
        """
        <style>
        /* Fundo Principal Grafite Profundo e Tipografia */
        .stApp {
            background-color: #0E1117;
            color: #F8FAFC;
        }
        /* Cartões Flutuantes (Estilo FM Data Hub & DataMB) */
        .til-card {
            background: linear-gradient(145deg, #1A1D24 0%, #14171D 100%);
            border: 1px solid #282D37;
            border-radius: 12px;
            padding: 18px 20px;
            margin-bottom: 14px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
        }
        .til-card-neon {
            background: linear-gradient(145deg, #1A1D24 0%, #12181B 100%);
            border: 1px solid rgba(0, 255, 127, 0.35);
            border-left: 4px solid #00FF7F;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 14px;
        }
        .til-card-alert {
            background: linear-gradient(145deg, #1A1D24 0%, #1F1518 100%);
            border: 1px solid rgba(255, 75, 75, 0.35);
            border-left: 4px solid #FF4B4B;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 14px;
        }
        /* Placar Estilo Sofascore Match Center */
        .sofascore-banner {
            background: linear-gradient(90deg, #131722 0%, #1E2433 50%, #131722 100%);
            border: 1px solid #2E3646;
            border-radius: 14px;
            padding: 22px 28px;
            margin-bottom: 20px;
            text-align: center;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
        }
        .sofascore-comp-badge {
            display: inline-block;
            background-color: rgba(0, 255, 127, 0.12);
            color: #00FF7F;
            border: 1px solid rgba(0, 255, 127, 0.4);
            padding: 4px 14px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        .sofascore-teams-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            max-width: 780px;
            margin: 0 auto;
        }
        .sofascore-team-name {
            font-size: 1.55rem;
            font-weight: 800;
            color: #F8FAFC;
            width: 38%;
        }
        .sofascore-score-box {
            background-color: #0E1117;
            border: 1px solid #38BDF8;
            border-radius: 10px;
            padding: 8px 22px;
            font-size: 1.75rem;
            font-weight: 900;
            color: #00FF7F;
            letter-spacing: 2px;
        }
        /* Metric Cards Customizados */
        .metric-label {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #94A3B8;
            margin-bottom: 4px;
            font-weight: 600;
        }
        .metric-value {
            font-size: 1.65rem;
            font-weight: 800;
            color: #F8FAFC;
            line-height: 1.15;
        }
        .metric-badge-pos {
            display: inline-block;
            margin-top: 6px;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.73rem;
            font-weight: 700;
            background-color: rgba(0, 255, 127, 0.14);
            color: #00FF7F;
        }
        .metric-badge-neg {
            display: inline-block;
            margin-top: 6px;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.73rem;
            font-weight: 700;
            background-color: rgba(255, 75, 75, 0.16);
            color: #FF4B4B;
        }
        .metric-badge-neu {
            display: inline-block;
            margin-top: 6px;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.73rem;
            font-weight: 700;
            background-color: rgba(56, 189, 248, 0.16);
            color: #38BDF8;
        }
        /* Barras Comparativas Estilo Sofascore */
        .pill-bar-container {
            margin: 10px 0 14px 0;
        }
        .pill-bar-header {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            font-weight: 700;
            margin-bottom: 5px;
            color: #E2E8F0;
        }
        .pill-bar-track {
            width: 100%;
            height: 9px;
            background-color: #262B36;
            border-radius: 999px;
            overflow: hidden;
            display: flex;
        }
        .pill-bar-fill-left {
            height: 100%;
            background: linear-gradient(90deg, #00FF7F, #10B981);
        }
        .pill-bar-fill-right {
            height: 100%;
            background: linear-gradient(90deg, #38BDF8, #2563EB);
        }
        /* Depth Chart Slot Estilo Simonetti Análises */
        .depth-slot {
            background-color: #161920;
            border: 1px solid #2A303C;
            border-top: 3px solid #38BDF8;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .depth-role-title {
            font-size: 0.8rem;
            font-weight: 800;
            color: #38BDF8;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(
    label: str, value: str, badge_text: str, status: str = "neu"
) -> None:
    badge_class = {
        "pos": "metric-badge-pos",
        "neg": "metric-badge-neg",
        "neu": "metric-badge-neu",
    }.get(status, "metric-badge-neu")

    st.markdown(
        f"""
        <div class="til-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <span class="{badge_class}">{badge_text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sofascore_stat_pill(
    metric_title: str,
    left_val: float,
    right_val: float,
    left_display: str,
    right_display: str,
    invert_advantage: bool = False,
) -> None:
    total = max(float(left_val) + float(right_val), 1e-6)
    left_pct = np.clip((float(left_val) / total) * 100.0, 5.0, 95.0)
    if invert_advantage:
        left_pct = 100.0 - left_pct
    right_pct = 100.0 - left_pct

    st.markdown(
        f"""
        <div class="pill-bar-container">
            <div class="pill-bar-header">
                <span style="color:#00FF7F;">{left_display}</span>
                <span style="color:#94A3B8; font-weight:600;">{metric_title}</span>
                <span style="color:#38BDF8;">{right_display}</span>
            </div>
            <div class="pill-bar-track">
                <div class="pill-bar-fill-left" style="width: {left_pct:.1f}%;"></div>
                <div class="pill-bar-fill-right" style="width: {right_pct:.1f}%;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# 2. GERENCIAMENTO DE DADOS E CACHE COM TRATAMENTO DE EXCEÇÕES
# =============================================================================
def get_loader() -> StatsBombDataLoader:
    """Instancia o loader garantindo sincronização imediata com SQLite."""
    return StatsBombDataLoader()


@st.cache_data(show_spinner=False)
def load_and_enrich_real_match(match_id: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    loader = get_loader()
    raw_df = loader.ingest_match_events(int(match_id))
    enriched_df = EventPreprocessor.process_match_events(raw_df)
    xt_df = ExpectedThreatModel.enrich_events_with_xt(enriched_df)
    chains_df = EventPreprocessor.build_possession_chains(xt_df)
    return xt_df, chains_df


@st.cache_data(show_spinner=False)
def load_and_enrich_simulated_match(
    home_team: str, away_team: str, match_id: int
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    loader = get_loader()
    raw_df = loader.generate_tactical_simulation_match(
        home_team=home_team, away_team=away_team, match_id=int(match_id)
    )
    enriched_df = EventPreprocessor.process_match_events(raw_df)
    xt_df = ExpectedThreatModel.enrich_events_with_xt(enriched_df)
    chains_df = EventPreprocessor.build_possession_chains(xt_df)
    return xt_df, chains_df


def _init_session_state() -> None:
    if "match_resolution" not in st.session_state:
        st.session_state["match_resolution"] = {
            "status": "FOUND_REAL",
            "is_simulation": False,
            "match_id": 3869685,
            "home_team": "Argentina",
            "away_team": "France",
            "candidate_matches": [],
            "user_message": "✅ Partida real encontrada na base de dados: **Argentina vs France** (Match ID `3869685`).",
        }
    if "last_searched_text" not in st.session_state:
        st.session_state["last_searched_text"] = "Argentina x França"
    if "simulation_confirmed" not in st.session_state:
        st.session_state["simulation_confirmed"] = False
    if "active_user_query" not in st.session_state:
        st.session_state["active_user_query"] = (
            "Monte uma tática para anular o meia adversário e explorar a transição defensiva."
        )
    if "latest_report_result" not in st.session_state:
        st.session_state["latest_report_result"] = None


def create_match_momentum_timeline(
    df_events: pd.DataFrame, team_a: str, team_b: str
) -> go.Figure:
    """
    Cria o gráfico de Momento da Partida (Attacking Momentum / xT + xG por janela de 5 min)
    inspirado no Sofascore Attack Momentum.
    """
    df = df_events.copy()
    df["time_bin"] = (df["minute"].fillna(0).astype(int) // 5) * 5
    bins = sorted(df["time_bin"].unique().tolist())

    momentum_vals = []
    colors = []
    hover_texts = []

    for b in bins:
        w = df[df["time_bin"] == b]
        w_a = w[w["team_name"] == team_a]
        w_b = w[w["team_name"] == team_b]

        press_a = (
            float(w_a.get("delta_xt", pd.Series(0.0)).clip(lower=0).sum()) * 100.0
            + float(w_a["is_progressive_action"].sum()) * 1.5
            + float(w_a.get("shot_statsbomb_xg", pd.Series(0.0)).fillna(0).sum()) * 25.0
        )
        press_b = (
            float(w_b.get("delta_xt", pd.Series(0.0)).clip(lower=0).sum()) * 100.0
            + float(w_b["is_progressive_action"].sum()) * 1.5
            + float(w_b.get("shot_statsbomb_xg", pd.Series(0.0)).fillna(0).sum()) * 25.0
        )
        net_mom = round(press_a - press_b, 2)
        momentum_vals.append(net_mom)
        colors.append("#00FF7F" if net_mom >= 0 else "#38BDF8")
        dom_team = team_a if net_mom >= 0 else team_b
        hover_texts.append(f"Min {b}-{b+5}: Dominância {dom_team} ({abs(net_mom):.1f})")

    fig = go.Figure(
        go.Bar(
            x=[f"{b}'" for b in bins],
            y=momentum_vals,
            marker_color=colors,
            hovertext=hover_texts,
            hoverinfo="text",
        )
    )
    fig.update_layout(
        title=f"Momento de Pressão Territorial (Sofascore Momentum): Verde = {team_a} | Azul = {team_b}",
        template="plotly_dark",
        paper_bgcolor="#1A1D24",
        plot_bgcolor="#1A1D24",
        height=290,
        margin=dict(l=25, r=25, t=45, b=25),
        xaxis_title="Minuto da Partida (Janelas de 5 min)",
        yaxis_title="Índice de Dominância (xT + xG)",
    )
    return fig


# =============================================================================
# 3. FUNÇÃO PRINCIPAL E ESTRUTURA EM 6 ABAS PROFISSIONAIS
# =============================================================================
def main() -> None:
    inject_elite_design_system()
    _init_session_state()
    loader = get_loader()

    # Cabeçalho Principal
    st.markdown(
        """
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <div>
                <h1 style="margin:0; font-size:2.0rem; font-weight:900; color:#F8FAFC;">
                    ⚽ TACTICAL INTELLIGENCE LAB <span style="color:#00FF7F; font-size:1.0rem; font-weight:700;">PRO SUITE</span>
                </h1>
                <p style="margin:2px 0 0 0; color:#94A3B8; font-size:0.9rem;">
                    Central Híbrida de Análise de Oposição, Grafos NetworkX, Expected Threat (xT), Machine Learning & IA Generativa Auditada
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # =========================================================================
    # BARRA DE CONTROLE DE CONFRONTO (PASSOS 1 E 2 BLINDADOS)
    # =========================================================================
    with st.container(border=True):
        col_mode, col_input, col_btn = st.columns([1.2, 2.3, 0.7])

        with col_mode:
            input_mode = st.selectbox(
                "🧭 Fonte do Confronto:",
                options=[
                    "Busca Inteligente (Texto Livre ou ID)",
                    "Catálogo Rápido (StatsBomb & Série A)",
                    "Upload de Arquivo (CSV / JSON)",
                ],
            )

        custom_uploaded_df = None

        with col_input:
            if input_mode == "Busca Inteligente (Texto Livre ou ID)":
                confronto_query = st.text_input(
                    "Digite o confronto, seleção ou clube (ex: 'Cruzeiro x Atlético-MG', 'Leverkusen', 'Brasil x Croácia', '3869685'):",
                    value=st.session_state["last_searched_text"],
                )
            elif input_mode == "Catálogo Rápido (StatsBomb & Série A)":
                try:
                    cat_df = loader.ensure_rich_catalog_in_db()
                    cat_records = (
                        loader.CURATED_OPEN_MATCHES
                        + cat_df.head(60).to_dict(orient="records")
                    )
                except Exception:
                    cat_records = loader.CURATED_OPEN_MATCHES

                seen_m = set()
                safe_catalog_map: Dict[str, str] = {}
                for c in cat_records:
                    mid_val = int(c.get("match_id", 3869685))
                    if mid_val in seen_m:
                        continue
                    seen_m.add(mid_val)
                    lbl = f"{c.get('competition_name', 'Liga')} — {c.get('home_team_name', 'Home')} vs {c.get('away_team_name', 'Away')} [ID {mid_val}]"
                    safe_catalog_map[lbl] = str(mid_val)

                chosen_label = st.selectbox(
                    "Selecione uma Partida do Catálogo:",
                    options=list(safe_catalog_map.keys()),
                )
                confronto_query = safe_catalog_map[chosen_label]
            else:
                uploaded = st.file_uploader(
                    "Envie um arquivo de eventos (.csv ou .json):",
                    type=["csv", "json"],
                )
                confronto_query = "Upload Customizado"
                if uploaded is not None:
                    try:
                        temp_path = Path("data/raw") / f"uploaded_{uploaded.name}"
                        temp_path.parent.mkdir(parents=True, exist_ok=True)
                        temp_path.write_bytes(uploaded.getvalue())
                        raw_custom = loader.ingest_custom_csv_or_json(
                            str(temp_path), match_id=999001
                        )
                        custom_uploaded_df = ExpectedThreatModel.enrich_events_with_xt(
                            EventPreprocessor.process_match_events(raw_custom)
                        )
                    except Exception as exc:
                        st.warning(
                            f"⚠️ Não foi possível processar o arquivo enviado: {exc}"
                        )

        with col_btn:
            st.write("")
            st.write("")
            btn_clicked = st.button(
                "🔍 Carregar Jogo", type="primary", use_container_width=True
            )

        text_changed = (
            input_mode != "Upload de Arquivo (CSV / JSON)"
            and confronto_query != st.session_state["last_searched_text"]
        )
        if btn_clicked or text_changed:
            if input_mode != "Upload de Arquivo (CSV / JSON)":
                try:
                    with st.spinner(
                        f"Localizando '{confronto_query}' na base de dados..."
                    ):
                        res = loader.resolve_user_match_input(confronto_query)
                        st.session_state["last_searched_text"] = confronto_query
                        st.session_state["match_resolution"] = res
                        st.session_state["simulation_confirmed"] = (
                            res["status"] == "FOUND_REAL"
                        )
                        st.session_state["latest_report_result"] = None
                except Exception as exc:
                    st.warning(
                        f"⚠️ Aviso ao consultar catálogo ({exc}). Mantendo última partida válida."
                    )

        resolution = st.session_state["match_resolution"]

        if input_mode == "Upload de Arquivo (CSV / JSON)":
            if custom_uploaded_df is not None:
                df_events = custom_uploaded_df
                df_chains = EventPreprocessor.build_possession_chains(df_events)
                current_match_id = 999001
                is_sim_mode = False
            else:
                st.info("Envie um arquivo CSV ou JSON válido acima para iniciar.")
                return
        elif resolution["status"] == "FOUND_REAL":
            candidates = resolution.get("candidate_matches", [])
            if len(candidates) > 1:
                cand_options = {
                    f"{c.get('competition_name', 'Liga')} — {c['home_team_name']} vs {c['away_team_name']} [ID {c['match_id']}]": int(
                        c["match_id"]
                    )
                    for c in candidates
                }
                selected_cand_label = st.selectbox(
                    "Foram encontradas múltiplas partidas para sua busca. Selecione o confronto:",
                    options=list(cand_options.keys()),
                )
                current_match_id = cand_options[selected_cand_label]
            else:
                current_match_id = int(resolution["match_id"])

            is_sim_mode = False
            try:
                with st.spinner("Processando malha geométrica e cadeias de posse..."):
                    df_events, df_chains = load_and_enrich_real_match(current_match_id)
            except Exception as exc:
                st.warning(
                    f"⚠️ Erro ao abrir a partida {current_match_id} ({exc}). Ativando contingência estruturada."
                )
                df_events, df_chains = load_and_enrich_simulated_match(
                    resolution.get("home_team", "Equipe A"),
                    resolution.get("away_team", "Equipe B"),
                    current_match_id,
                )
                is_sim_mode = True
        else:
            st.warning(resolution["user_message"])
            if st.button(
                "⚡ Ativar Simulação Tática Estruturada deste Confronto",
                type="primary",
            ):
                st.session_state["simulation_confirmed"] = True
                st.session_state["latest_report_result"] = None

            if not st.session_state["simulation_confirmed"]:
                return

            current_match_id = int(resolution["match_id"])
            is_sim_mode = True
            with st.spinner("Construindo simulação tática estruturada..."):
                df_events, df_chains = load_and_enrich_simulated_match(
                    resolution["home_team"],
                    resolution["away_team"],
                    current_match_id,
                )

    teams = df_events["team_name"].dropna().unique().tolist()
    if not teams:
        st.warning("Nenhuma equipe identificada nos eventos carregados.")
        return

    all_match_players = (
        df_events["player_name"].dropna().astype(str).unique().tolist()
    )

    # =========================================================================
    # BARRA LATERAL: SELETOR DE EQUIPE E TELEMETRIA DO SISTEMA
    # =========================================================================
    st.sidebar.markdown("### 🎯 Controle Tático da Sessão")
    target_team = st.sidebar.selectbox(
        "Equipe em Foco Analítico:", options=teams, index=0
    )
    opponent_teams = [t for t in teams if t != target_team]
    opponent_name = opponent_teams[0] if opponent_teams else "Adversário"

    # Cálculo seguro dos sumários de ambas as equipes para comparativos Sofascore
    try:
        tactical_summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
            df_events, df_chains, target_team
        )
        opp_summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
            df_events, df_chains, opponent_name
        )
        aerial_team = BenchmarkDiscrepancyEngine.extract_aerial_and_crossing_stats(
            df_events, target_team
        )
        aerial_opp = BenchmarkDiscrepancyEngine.extract_aerial_and_crossing_stats(
            df_events, opponent_name
        )
    except Exception as exc:
        st.warning(f"Erro ao consolidar métricas coletivas: {exc}")
        return

    d_org = tactical_summary["defensive_organization"]
    o_org = tactical_summary["offensive_organization"]
    o_tr = tactical_summary["offensive_transition"]
    d_tr = tactical_summary["defensive_transition"]
    mid = tactical_summary["midfield_control"]
    sp = tactical_summary["set_pieces"]

    opp_d_org = opp_summary["defensive_organization"]
    opp_o_org = opp_summary["offensive_organization"]

    # Gols reais registrados nos eventos de Shot (Goal)
    goals_target = int(
        (
            (df_events["team_name"] == target_team)
            & (df_events["type_name"] == "Shot")
            & (df_events.get("shot_outcome_name", pd.Series("")) == "Goal")
        ).sum()
    )
    goals_opp = int(
        (
            (df_events["team_name"] == opponent_name)
            & (df_events["type_name"] == "Shot")
            & (df_events.get("shot_outcome_name", pd.Series("")) == "Goal")
        ).sum()
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f"""
        <div class="til-card">
            <div class="metric-label">Telemetria SQLite</div>
            <div style="font-size:0.88rem; color:#E2E8F0; line-height:1.7;">
                • <b>Match ID:</b> <code>{current_match_id}</code><br>
                • <b>Modo:</b> <code>{'Simulação Lab' if is_sim_mode else 'Oficial Auditado'}</code><br>
                • <b>Eventos Processados:</b> <code>{len(df_events)}</code><br>
                • <b>Cadeias de Posse:</b> <code>{len(df_chains)}</code><br>
                • <b>Atletas Mapeados:</b> <code>{len(all_match_players)}</code>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # =========================================================================
    # ESTRUTURAÇÃO DEFINITIVA NAS 6 ABAS PROFISSIONAIS
    # =========================================================================
    tabs = st.tabs(
        [
            "📊 1. Match Center & Momento",
            "🕸️ 2. Data Hub, Grafos & xT",
            "🤖 3. Machine Learning & Risco",
            "📋 4. Elenco, Scout & Substituições",
            "📈 5. DNA Histórico & Vídeo 2D",
            "🧠 6. Consultor IA & Exportação",
        ]
    )

    # -------------------------------------------------------------------------
    # ABA 1: MATCH CENTER & MOMENTO DA PARTIDA (ESTILO SOFASCORE)
    # -------------------------------------------------------------------------
    with tabs[0]:
        badge_mode = (
            "SIMULAÇÃO TÁTICA DE LABORATÓRIO"
            if is_sim_mode
            else f"DADOS OFICIAIS AUDITADOS • MATCH ID {current_match_id}"
        )
        st.markdown(
            f"""
            <div class="sofascore-banner">
                <div class="sofascore-comp-badge">{badge_mode}</div>
                <div class="sofascore-teams-row">
                    <div class="sofascore-team-name" style="text-align:right;">{target_team}</div>
                    <div class="sofascore-score-box">{goals_target} - {goals_opp}</div>
                    <div class="sofascore-team-name" style="text-align:left;">{opponent_name}</div>
                </div>
                <div style="margin-top:10px; color:#94A3B8; font-size:0.85rem;">
                    xG Esperado: <b style="color:#00FF7F;">{o_org['total_xg']:.2f}</b> vs <b style="color:#38BDF8;">{opp_o_org['total_xg']:.2f}</b>
                    &nbsp;|&nbsp; Perfil de Bloco ({target_team}): <b>{d_org['block_profile']}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Fileira de 6 Metric Cards com Indicadores de Status
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1:
            render_metric_card(
                "PPDA (Pressão)",
                f"{d_org['ppda']}",
                "Pressão Alta" if d_org["ppda"] < 9.0 else d_org["block_profile"],
                "pos" if d_org["ppda"] < 9.5 else "neu",
            )
        with m2:
            render_metric_card(
                "Altura da Linha",
                f"{d_org['avg_defensive_engagement_height_m']} m",
                f"Disp: ±{d_org['longitudinal_dispersion_m']}m",
                "pos"
                if d_org["avg_defensive_engagement_height_m"] >= 42.0
                else "neu",
            )
        with m3:
            render_metric_card(
                "Field Tilt (3º Final)",
                f"{mid['field_tilt_pct']}%",
                "Domínio Territorial"
                if mid["field_tilt_pct"] >= 52.0
                else "Bloco Reativo",
                "pos" if mid["field_tilt_pct"] >= 50.0 else "neg",
            )
        with m4:
            render_metric_card(
                "Infiltrações Zona 14",
                f"{o_org['zone_14_entries']}",
                f"{o_org['penalty_box_entries']} entradas na área",
                "pos" if o_org["zone_14_entries"] >= 8 else "neu",
            )
        with m5:
            render_metric_card(
                "Gegenpress (5s)",
                f"{d_tr['post_loss_5s_press_reaction_pct']}%",
                f"{d_tr['post_loss_5s_recoveries_count']} recup. imediatas",
                "pos"
                if d_tr["post_loss_5s_press_reaction_pct"] >= 45.0
                else "neg",
            )
        with m6:
            render_metric_card(
                "Duelos Aéreos (Ataque)",
                f"{aerial_team['aerial_win_pct']}%",
                f"{aerial_team['aerial_duels_won']}/{aerial_team['aerial_duels_total']} ganhos",
                "pos" if aerial_team["aerial_win_pct"] >= 52.0 else "neu",
            )

        # Gráfico Attack Momentum (Sofascore) + Pílulas Comparativas Lado a Lado
        col_mom, col_pills = st.columns([1.35, 1.0])
        with col_mom:
            try:
                fig_mom = create_match_momentum_timeline(
                    df_events, target_team, opponent_name
                )
                st.plotly_chart(fig_mom, use_container_width=True)
            except Exception as exc:
                st.warning(f"Não foi possível renderizar linha do tempo: {exc}")

            try:
                fig_corr = TacticalVisualizer.create_corridor_vulnerability_plotly(
                    d_org, target_team
                )
                st.plotly_chart(fig_corr, use_container_width=True)
            except Exception as exc:
                st.warning(f"Aviso ao gerar gráfico de corredores: {exc}")

        with col_pills:
            st.markdown(
                f"""
                <div class="til-card">
                    <h4 style="margin-top:0; color:#F8FAFC;">⚡ Comparativo Direto (Pílulas Sofascore)</h4>
                    <p style="font-size:0.8rem; color:#94A3B8; margin-bottom:12px;">
                        Verde: <b>{target_team}</b> &nbsp;|&nbsp; Azul: <b>{opponent_name}</b>
                    </p>
                """,
                unsafe_allow_html=True,
            )
            render_sofascore_stat_pill(
                "Expected Goals (xG)",
                o_org["total_xg"],
                opp_o_org["total_xg"],
                f"{o_org['total_xg']:.2f}",
                f"{opp_o_org['total_xg']:.2f}",
            )
            render_sofascore_stat_pill(
                "Domínio Territorial (Field Tilt)",
                mid["field_tilt_pct"],
                100.0 - mid["field_tilt_pct"],
                f"{mid['field_tilt_pct']:.1f}%",
                f"{100.0 - mid['field_tilt_pct']:.1f}%",
            )
            render_sofascore_stat_pill(
                "Passes Completos (Precisão)",
                o_org["total_passes"],
                opp_o_org["total_passes"],
                f"{o_org['total_passes']} ({o_org['overall_pass_completion_pct']}%)",
                f"{opp_o_org['total_passes']} ({opp_o_org['overall_pass_completion_pct']}%)",
            )
            render_sofascore_stat_pill(
                "Intensidade PPDA (Menor = Mais Agressivo)",
                d_org["ppda"],
                opp_d_org["ppda"],
                f"{d_org['ppda']}",
                f"{opp_d_org['ppda']}",
                invert_advantage=True,
            )
            render_sofascore_stat_pill(
                "Entradas na Grande Área",
                o_org["penalty_box_entries"],
                opp_o_org["penalty_box_entries"],
                f"{o_org['penalty_box_entries']}",
                f"{opp_o_org['penalty_box_entries']}",
            )
            render_sofascore_stat_pill(
                "Vitórias Aéreas Ofensivas",
                aerial_team["aerial_duels_won"],
                aerial_opp["aerial_duels_won"],
                f"{aerial_team['aerial_duels_won']} ({aerial_team['aerial_win_pct']}%)",
                f"{aerial_opp['aerial_duels_won']} ({aerial_opp['aerial_win_pct']}%)",
            )
            st.markdown("</div>", unsafe_allow_html=True)

            # Conclusões Simples por Discrepância Estatística
            disc_info = BenchmarkDiscrepancyEngine.generate_plain_language_discrepancy_conclusions(
                df_events=df_events,
                phases_metrics=tactical_summary,
                passing_network=PassingNetworkAnalyzer.build_pass_network(
                    df_events, target_team, until_first_sub=True
                )["graph_metrics"],
                clustering_data=SpatialTacticalClustering.analyze_turnover_clusters(
                    df_events, target_team
                ),
                target_team=target_team,
                opponent_team=opponent_name,
            )
            st.markdown("#### 💡 Conclusões Diretas por Discrepância (Linguagem Simples)")
            for conclusion in disc_info.get("plain_language_conclusions", []):
                card_style = (
                    "til-card-alert" if "🔴" in conclusion else "til-card-neon"
                )
                st.markdown(
                    f'<div class="{card_style}" style="font-size:0.88rem;">{conclusion}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("#### 🛡️ Diagnósticos Estruturados Causa-Efeito (Plano A e Plano B)")
        try:
            diags = TacticalDiagnosticEngine.generate_comprehensive_diagnostics(
                df_events, df_chains, target_team
            )
            for d in diags:
                with st.expander(
                    f"[{d['evidence_strength']}] {d['problem_title']} — Setor: {d['pitch_zone']} (Amostra N={d['sample_size']})",
                    expanded=True,
                ):
                    st.markdown(
                        f"**Diagnóstico Tático:** {d['tactical_interpretation']}"
                    )
                    c_pa, c_pb = st.columns(2)
                    c_pa.success(f"**Plano A:** {d['recommendation_plan_a']}")
                    c_pb.info(f"**Plano B:** {d['recommendation_alternative_b']}")
                    st.caption(
                        f"⚠️ Risco da Intervenção: {d['recommendation_risks']} | Limitação: {d['data_limitations']}"
                    )
        except Exception as exc:
            st.warning(f"Não foi possível gerar os cards de diagnóstico: {exc}")

    # -------------------------------------------------------------------------
    # ABA 2: CENTRAL DE DADOS TÁTICOS & xT (ESTILO FOOTBALL MANAGER DATA HUB)
    # -------------------------------------------------------------------------
    with tabs[1]:
        st.subheader(
            f"🕸️ Central de Dados Táticos, Topologia NetworkX & Expected Threat (xT) — {target_team}"
        )
        until_sub = st.checkbox(
            "Recortar rede até a 1ª substituição (preserva estrutura posicional dos 11 titulares)",
            value=True,
        )
        try:
            net_res = PassingNetworkAnalyzer.build_pass_network(
                df_events, target_team, until_first_sub=until_sub, min_pass_count=2
            )
            gm = net_res["graph_metrics"]
            xt_sum = ExpectedThreatModel.compute_team_xt_summary(
                df_events, target_team
            )

            h1, h2, h3, h4 = st.columns(4)
            with h1:
                render_metric_card(
                    "Estrutura Real em Posse",
                    str(gm.get("inferred_positional_structure", "4-3-3")),
                    f"Até min {gm.get('analyzed_until_minute', 90.0)}",
                    "pos",
                )
            with h2:
                render_metric_card(
                    "Pivô Principal (Betweenness)",
                    PlayerNameNormalizer.to_common_name(
                        str(gm.get("primary_bridge_player_betweenness", "N/A"))
                    ),
                    f"Score: {gm.get('primary_bridge_score', 0.0)}",
                    "pos",
                )
            with h3:
                render_metric_card(
                    "Conector Gravitacional",
                    PlayerNameNormalizer.to_common_name(
                        str(gm.get("primary_gravity_playmaker_pagerank", "N/A"))
                    ),
                    f"Share máx: {gm.get('max_player_pass_share_pct', 0.0)}%",
                    "neu",
                )
            with h4:
                render_metric_card(
                    "Expected Threat (+xT)",
                    f"+{xt_sum.get('total_xt_generated', 0.0):.3f}",
                    f"Densidade Grafo: {gm.get('network_density', 0.0)}",
                    "pos",
                )

            col_net, col_xt = st.columns(2)
            with col_net:
                fig_net = TacticalVisualizer.plot_passing_network(net_res)
                st.pyplot(fig_net)
                plt.close(fig_net)

            with col_xt:
                fig_xt = TacticalVisualizer.plot_progression_and_xt_map(
                    df_events, target_team
                )
                st.pyplot(fig_xt)
                plt.close(fig_xt)

            if not net_res["nodes_df"].empty:
                st.markdown(
                    "#### 📊 Matriz Topológica de Centralidades (`NetworkX`)"
                )
                st.dataframe(
                    net_res["nodes_df"][
                        [
                            "player_name",
                            "position_name",
                            "avg_x",
                            "avg_y",
                            "passes_made",
                            "passes_received",
                            "progressive_passes_made",
                            "betweenness_centrality",
                            "pagerank_centrality",
                            "clustering_coeff",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
        except Exception as exc:
            st.warning(f"Erro ao renderizar grafos e mapa xT: {exc}")

    # -------------------------------------------------------------------------
    # ABA 3: MACHINE LEARNING & ALERTAS DE RISCO (ESTILO DATAMB / CIES)
    # -------------------------------------------------------------------------
    with tabs[2]:
        st.subheader(
            f"🤖 Laboratório de Machine Learning (K-Means, DBSCAN & XGBoost) — {target_team}"
        )
        try:
            km_res = SpatialTacticalClustering.analyze_turnover_clusters(
                df_events, target_team
            )
            db_res = SpatialTacticalClustering.analyze_recovery_density_dbscan(
                df_events, target_team
            )

            col_map, col_ml = st.columns([1.15, 1.0])
            with col_map:
                fig_cl = TacticalVisualizer.plot_spatial_clusters_and_press_traps(
                    df_events,
                    {"kmeans_turnovers": km_res, "dbscan_recoveries": db_res},
                    target_team,
                )
                st.pyplot(fig_cl)
                plt.close(fig_cl)

            with col_ml:
                risk_c = km_res.get("highest_risk_exposure_cluster") or {}
                st.markdown(
                    f"""
                    <div class="til-card-alert">
                        <div class="metric-label">Zona Crítica de Risco Ponderado por Exposição (K-Means)</div>
                        <div style="font-size:1.25rem; font-weight:800; color:#FF4B4B;">
                            {risk_c.get('tactical_third', 'N/A')} • {risk_c.get('tactical_corridor', 'N/A')} (Zona {risk_c.get('zone_18', '-')})
                        </div>
                        <div style="font-size:0.88rem; color:#E2E8F0; margin-top:6px;">
                            Taxa de Perda por Toque: <b>{risk_c.get('turnover_rate_per_touch_pct', 0.0)}%</b>
                            ({risk_c.get('local_radius_turnovers_numerator', 0)} perdas em {risk_c.get('local_radius_touches_denominator', 0)} toques locais) |
                            K Ótimo = <code>{km_res.get('optimal_k', 0)}</code> (Silhouette: <code>{km_res.get('silhouette_score', 0.0)}</code>)
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if km_res.get("clusters"):
                    st.dataframe(
                        pd.DataFrame(km_res["clusters"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                st.markdown(
                    "#### 🎯 Classificador Supervisionado de Perigo de Posse (`XGBoost`)"
                )
                clf = PossessionDangerClassifier()
                has_trained = clf.load_models()
                if st.button(
                    "⚡ Recalibrar / Treinar Modelo XGBoost na Partida Atual",
                    use_container_width=True,
                ):
                    with st.spinner(
                        "Treinando XGBoost e Regressão Logística com validação..."
                    ):
                        clf.train_and_evaluate(df_chains)
                        has_trained = True

                if has_trained and clf.xgb_model is not None:
                    m_xgb = clf.latest_metrics.get("xgboost_metrics", {})
                    x1, x2, x3 = st.columns(3)
                    with x1:
                        render_metric_card(
                            "ROC-AUC (Teste)",
                            f"{m_xgb.get('test_roc_auc', 0.0)}",
                            "Poder Discriminante",
                            "pos",
                        )
                    with x2:
                        render_metric_card(
                            "F1-Score",
                            f"{m_xgb.get('test_f1_score', 0.0)}",
                            f"Precisão: {m_xgb.get('test_precision', 0.0)}",
                            "neu",
                        )
                    with x3:
                        render_metric_card(
                            "Brier Score",
                            f"{m_xgb.get('test_brier_score', 0.0)}",
                            "Calibração Prob.",
                            "pos"
                            if float(m_xgb.get("test_brier_score", 0.2)) < 0.22
                            else "neu",
                        )

                    pred_res = clf.predict_possession_probabilities(
                        df_chains, target_team=target_team
                    )
                    if pred_res.get("status") == "OK":
                        st.markdown(
                            f"""
                            <div class="til-card-neon">
                                <b>Corredor Inicial de Maior Expectativa Probabilística ({target_team}):</b>
                                <span style="color:#00FF7F; font-weight:800;">{pred_res['highest_probability_start_corridor']}</span>
                                (Média Preditiva: <b>{pred_res['avg_predicted_danger_prob_pct']}%</b> | Real: <b>{pred_res['actual_danger_rate_pct']}%</b>)
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.dataframe(
                            pd.DataFrame(pred_res["corridor_probabilities"]).T,
                            use_container_width=True,
                        )
        except Exception as exc:
            st.warning(f"Aviso no módulo de Machine Learning: {exc}")

    # -------------------------------------------------------------------------
    # ABA 4: PLANEJADOR DE ELENCO, SCOUT & SUBSTITUIÇÕES (ESTILO SIMONETTI ANÁLISES)
    # -------------------------------------------------------------------------
    with tabs[3]:
        st.subheader(
            f"📋 Planejador de Elenco (Depth Chart), Scout Individual & Substituições — {target_team}"
        )
        try:
            players_df = PlayerTacticalEvaluator.evaluate_team_players(
                df_events, target_team
            )

            # 1. Matriz de Profundidade por Setor (Estilo Simonetti Análises Depth Chart)
            st.markdown("#### 🧩 Matriz de Profundidade e Impacto por Setor (Depth Chart)")
            d_cols = st.columns(4)
            sectors_map = [
                ("Goleiro & Linha Defensiva", ["Goalkeeper", "Back"]),
                ("Volantes & Construção Central", ["Defensive Midfield", "Center Midfield"]),
                ("Meias-Armadores & Extremos", ["Attacking Midfield", "Wing", "Left Midfield", "Right Midfield"]),
                ("Centroavantes & Ataque", ["Forward", "Striker"]),
            ]
            for idx_s, (sec_title, keywords) in enumerate(sectors_map):
                with d_cols[idx_s]:
                    st.markdown(
                        f'<div class="depth-slot"><div class="depth-role-title">{sec_title}</div>',
                        unsafe_allow_html=True,
                    )
                    sec_players = players_df[
                        players_df["position_name"].apply(
                            lambda p: any(k.lower() in str(p).lower() for k in keywords)
                        )
                    ]
                    if sec_players.empty:
                        st.caption("Sem atletas registrados neste filtro.")
                    else:
                        for _, pr in sec_players.head(4).iterrows():
                            st.markdown(
                                f"**{pr['player_name']}** (`{pr['estimated_minutes_active']}'`)  \n"
                                f"<span style='color:#00FF7F; font-size:0.8rem;'>Score: {pr['tactical_impact_score']}</span> | "
                                f"<span style='color:#94A3B8; font-size:0.8rem;'>xT: +{pr['xt_generated']:.3f} | Passes: {pr['pass_accuracy_pct']}%</span>",
                                unsafe_allow_html=True,
                            )
                    st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("#### 📊 Tabela Analítica Completa de Desempenho Individual")
            st.dataframe(players_df, use_container_width=True, hide_index=True)

            # 2. Relatório Individual Exclusivo de Jogador (Qualquer equipe da partida)
            st.markdown("---")
            st.markdown(
                "#### 🕵️‍♂️ Dossiê Individual Exclusivo de Atleta (Scout & Como Anular / Potencializar)"
            )
            col_sel_p, col_btn_p = st.columns([2.2, 1.0])
            with col_sel_p:
                selected_scout_player = st.selectbox(
                    "Selecione qualquer jogador da partida (de ambas as equipes):",
                    options=all_match_players,
                )
            with col_btn_p:
                st.write("")
                st.write("")
                gen_player_rep = st.button(
                    "📄 Gerar Dossiê Deste Atleta",
                    type="primary",
                    use_container_width=True,
                )

            if gen_player_rep and selected_scout_player:
                p_md = TacticalReportBuilder.build_dedicated_player_scouting_report(
                    df_events, selected_scout_player
                )
                st.markdown(
                    f'<div class="til-card-neon">{p_md}</div>',
                    unsafe_allow_html=True,
                )
                st.download_button(
                    f"📥 Baixar Relatório de {selected_scout_player} (.md)",
                    data=p_md,
                    file_name=f"scout_{selected_scout_player.lower().replace(' ', '_')}.md",
                    mime="text/markdown",
                )

            # 3. Comparador Head-to-Head + Motor de Substituições
            col_rad, col_sub = st.columns([1.15, 1.0])
            with col_rad:
                st.markdown("#### ⚔️ Comparador Direto Head-to-Head (Radar DataMB)")
                if len(players_df) >= 2:
                    p_list = players_df["player_name"].tolist()
                    c_pa, c_pb = st.columns(2)
                    player_a = c_pa.selectbox("Atleta A:", options=p_list, index=0)
                    player_b = c_pb.selectbox("Atleta B:", options=p_list, index=1)
                    fig_radar = TacticalVisualizer.create_player_comparison_radar_plotly(
                        players_df, player_a, player_b
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

            with col_sub:
                st.markdown(
                    "#### 🔄 Motor Prescritivo de Substituições (Queda Pós-Minuto 60)"
                )
                subs_res = PlayerTacticalEvaluator.recommend_tactical_substitutions(
                    df_events, target_team
                )
                if subs_res["recommended_substitutions"]:
                    for rec in subs_res["recommended_substitutions"]:
                        st.markdown(
                            f"""
                            <div class="til-card-alert">
                                <div style="font-weight:800; color:#FF4B4B; font-size:1.05rem;">
                                    ⚠️ Substituir: {rec['candidate_out']} ({rec['position']}) — Prioridade {rec['priority_score']}
                                </div>
                                <p style="font-size:0.86rem; margin:6px 0;"><b>Evidência:</b> {' '.join(rec['tactical_reasons'])}</p>
                                <p style="font-size:0.86rem; margin:6px 0; color:#00FF7F;"><b>Perfil Ideal para Entrar:</b> {rec['ideal_replacement_profile']}</p>
                                <p style="font-size:0.78rem; color:#94A3B8; margin:0;"><b>Risco:</b> {' '.join(rec['structural_risks_of_substitution'])}</p>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                else:
                    st.success(
                        "✅ Nenhum titular apresentou degradação técnica crítica (>12% de queda com turnovers) após o minuto 60."
                    )
                st.caption(subs_res["data_limitations_notice"])
        except Exception as exc:
            st.warning(f"Erro ao processar módulo de elenco e substituições: {exc}")

    # -------------------------------------------------------------------------
    # ABA 5: HISTÓRICO MULTI-JOGOS & DNA DO CLUBE (ESTILO CIES / OPTA)
    # -------------------------------------------------------------------------
    with tabs[4]:
        st.subheader(
            "📈 Análise Longitudinal Multi-Jogos (DNA do Clube) & Laboratório de Vídeo 2D"
        )
        c_hist_team, c_hist_n, c_hist_btn = st.columns([1.8, 0.7, 1.1])
        with c_hist_team:
            history_team_input = st.text_input(
                "Clube ou Seleção para Auditoria Histórica Multi-Partidas (ex: 'Cruzeiro', 'Bayer Leverkusen', 'Argentina', 'Palmeiras'):",
                value=target_team,
            )
        with c_hist_n:
            max_hist_games = int(
                st.number_input("Jogos na Amostra:", min_value=2, max_value=10, value=4)
            )
        with c_hist_btn:
            st.write("")
            st.write("")
            run_hist_btn = st.button(
                "📊 Auditar Histórico do Clube",
                type="primary",
                use_container_width=True,
            )

        if run_hist_btn:
            try:
                with st.spinner(
                    f"Consolidando série histórica de '{history_team_input}'..."
                ):
                    canon_team, m_map, _ = loader.find_all_matches_for_team(
                        history_team_input, max_matches=max_hist_games
                    )
                    if not m_map:
                        st.warning(
                            f"Não foram encontradas múltiplas partidas catalogadas para '{history_team_input}'."
                        )
                    else:
                        trends = MultiMatchTrendAnalyzer.analyze_team_across_matches(
                            m_map, target_team=canon_team
                        )
                        hist_md = TacticalReportBuilder.build_multi_match_team_history_report(
                            trends
                        )
                        st.success(
                            f"✅ Base Histórica Consolidada: **{canon_team}** ({trends['matches_analyzed']} jogos processados)."
                        )
                        st.dataframe(
                            pd.DataFrame(trends["per_match_table"]),
                            use_container_width=True,
                            hide_index=True,
                        )
                        st.markdown(hist_md)
                        st.download_button(
                            f"📥 Baixar Dossiê Histórico de {canon_team} (.md)",
                            data=hist_md,
                            file_name=f"dna_historico_{canon_team.lower().replace(' ', '_')}.md",
                            mime="text/markdown",
                        )
            except Exception as exc:
                st.warning(f"Erro ao construir histórico multi-jogos: {exc}")

        st.markdown("---")
        st.subheader(
            "🎥 Visão Computacional & Transformação Homográfica Planar 2D (SVD)"
        )
        try:
            demo_vid = PitchHomographyProjector.run_synthetic_broadcast_frame_demo()
            cm = demo_vid["compactness_metrics"]
            v1, v2, v3, v4 = st.columns(4)
            with v1:
                render_metric_card(
                    "Altura Linha Defensiva",
                    f"{cm['defensive_line_height_m']} m",
                    "Frame Projetado",
                    "neu",
                )
            with v2:
                render_metric_card(
                    "Distância Defesa-Meio",
                    f"{cm['inter_line_distance_def_to_mid_m']} m",
                    cm["compactness_diagnosis"],
                    "pos"
                    if cm["inter_line_distance_def_to_mid_m"] <= 14.5
                    else "neg",
                )
            with v3:
                render_metric_card(
                    "Maior Gap Horizontal",
                    f"{cm['max_horizontal_defender_gap_m']} m",
                    f"Média: {cm['avg_horizontal_defender_gap_m']} m",
                    "neu",
                )
            with v4:
                render_metric_card(
                    "Polígono Convexo",
                    f"{cm['convex_hull_area_m2']} m²",
                    f"{cm['players_detected_in_frame']} atletas no frame",
                    "pos",
                )
            st.dataframe(
                demo_vid["projected_players_df"],
                use_container_width=True,
                hide_index=True,
            )
        except Exception as exc:
            st.warning(f"Aviso no módulo de homografia: {exc}")

    # -------------------------------------------------------------------------
    # ABA 6: DOSSIÊ IA, AUDITORIA & EXPORTAÇÃO (GEMINI + GUARDRAILS)
    # -------------------------------------------------------------------------
    with tabs[5]:
        st.subheader(
            f"🧠 Consultor Tático Inteligente (Rede Neural MLP + Gemini + Guardrail Numérico) — {target_team}"
        )

        team_players_list = (
            df_events[df_events["team_name"] == target_team]["player_name"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )
        star_example = team_players_list[0] if team_players_list else "Jogador X"

        quick_suggestions = [
            "Personalizado (Digitar comando livre abaixo)",
            "Monte uma tática para anular o meia adversário e cortar suas conexões.",
            f"Monte uma tática para anular o jogador {star_example} e cortar suas linhas de passe.",
            f"Analise as vulnerabilidades na transição defensiva de {target_team} e onde mais perdem a posse.",
            f"Analise toda a organização defensiva de {target_team} e identifique os corredores mais expostos.",
            f"Como devemos pressionar a saída de bola de {target_team} e quem é o pivô da rede de passes?",
            f"Sugira uma substituição para corrigir queda de rendimento pós-minuto 60 em {target_team}.",
            f"Monte um plano de jogo e relatório tático completo sobre {target_team}.",
        ]
        chosen_suggestion = st.selectbox(
            "Comandos Rápidos de Comissão Técnica (ou escolha 'Personalizado'):",
            options=quick_suggestions,
            index=1,
        )

        default_query_text = (
            st.session_state["active_user_query"]
            if chosen_suggestion == "Personalizado (Digitar comando livre abaixo)"
            else chosen_suggestion
        )

        user_query_input = st.text_input(
            "Pergunta ou Comando Tático em Linguagem Natural:",
            value=default_query_text,
        )

        c_opt1, c_opt2 = st.columns([2.2, 1.0])
        with c_opt1:
            use_gemini = st.checkbox(
                "🤖 Utilizar API Google Gemini (se GEMINI_API_KEY estiver no .env; caso contrário utiliza o Motor Determinístico Local Auditado)",
                value=True,
            )
        with c_opt2:
            run_query_btn = st.button(
                "🚀 Gerar Dossiê Tático Auditado",
                type="primary",
                use_container_width=True,
            )

        if run_query_btn:
            st.session_state["active_user_query"] = user_query_input
            try:
                with st.spinner(
                    "Interpretando comando via Rede Neural MLP, cruzando discrepâncias e auditando números..."
                ):
                    evidence_pkg = TacticalReportBuilder.assemble_evidence_package(
                        df_events=df_events,
                        df_chains=df_chains,
                        target_team=target_team,
                        match_id=current_match_id,
                        user_query=user_query_input,
                        is_simulation=is_sim_mode,
                    )
                    analyst = GenerativeTacticalAnalyst()
                    rep_res = analyst.generate_tactical_report(
                        evidence_pkg, prefer_llm=use_gemini
                    )
                    exported_paths = TacticalReportBuilder.export_report_files(
                        rep_res["report_markdown"],
                        output_prefix=f"data/processed/relatorio_{current_match_id}_{target_team.lower().replace(' ', '_')}",
                    )
                    st.session_state["latest_report_result"] = {
                        "evidence": evidence_pkg,
                        "report": rep_res,
                        "paths": exported_paths,
                    }
            except Exception as exc:
                st.warning(f"Erro ao gerar dossiê tático: {exc}")

        if st.session_state["latest_report_result"] is not None:
            saved = st.session_state["latest_report_result"]
            ev_meta = saved["evidence"]["metadata"]
            rep_res = saved["report"]
            audit = rep_res["hallucination_audit"]

            st.markdown(
                f"""
                <div class="til-card-neon">
                    <b>Foco Semântico (Rede Neural MLP):</b> <code>{ev_meta['detected_focus']}</code> (Confiança: <b>{ev_meta.get('nlp_confidence_pct', 100.0)}%</b>) &nbsp;|&nbsp;
                    <b>Alvos Identificados:</b> <code>{ev_meta.get('matched_players_in_query') or 'Coletivo/Setorial'}</code> &nbsp;|&nbsp;
                    <b>Motor:</b> <code>{rep_res['engine_used']}</code> &nbsp;|&nbsp;
                    <b>Guardião Anti-Alucinação:</b> <span style="color:#00FF7F; font-weight:800;">{'APROVADO (100% Grounded)' if audit['is_grounded'] else 'REVISADO'}</span>
                    ({audit['verified_decimals_count']} métricas decimais auditadas)
                </div>
                """,
                unsafe_allow_html=True,
            )

            dl1, dl2 = st.columns(2)
            dl1.download_button(
                "📥 Baixar Relatório Completo (.md)",
                data=rep_res["report_markdown"],
                file_name=f"dossie_tatico_{target_team.lower().replace(' ', '_')}.md",
                mime="text/markdown",
                use_container_width=True,
            )
            html_str = Path(saved["paths"]["html_path"]).read_text(encoding="utf-8")
            dl2.download_button(
                "📥 Baixar Relatório Formatado para Impressão (.html)",
                data=html_str,
                file_name=f"dossie_tatico_{target_team.lower().replace(' ', '_')}.html",
                mime="text/html",
                use_container_width=True,
            )

            st.markdown("---")
            st.markdown(rep_res["report_markdown"])

            with st.expander("🔍 Inspecionar Pacote JSON Imutável de Evidências (Single Source of Truth)"):
                st.json(saved["evidence"])


if __name__ == "__main__":
    main()