"""Tema visual (dark mode) do Tactical Intelligence Lab."""

import streamlit as st

CSS = """
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

        /* ---------- Novos estilos: navegação, selos e estados vazios ---------- */
        section[data-testid="stSidebar"] { background-color: #0B0E14; border-right: 1px solid #1F2430; }
        div[role="radiogroup"] label { font-weight: 700; }
        .til-level-badge {
            display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 0.76rem;
            font-weight: 800; letter-spacing: 0.04em; border: 1px solid currentColor; margin-bottom: 8px;
        }
        .til-section-title { font-size: 1.35rem; font-weight: 900; color: #F8FAFC; margin: 4px 0 2px 0; }
        .til-section-sub { color: #94A3B8; font-size: 0.88rem; margin-bottom: 14px; }
        .til-empty {
            border: 1px dashed #334155; border-radius: 12px; padding: 22px; text-align: center;
            color: #94A3B8; background: #11151C; margin: 10px 0 16px 0;
        }
        .til-match-card {
            background: #141922; border: 1px solid #263042; border-radius: 12px; padding: 12px 14px; margin: 8px 0;
        }
        .til-match-card .teams { font-weight: 800; color: #F8FAFC; font-size: 0.98rem; }
        .til-match-card .meta { color: #94A3B8; font-size: 0.78rem; margin-top: 3px; }
        .til-kpi { background:#141922; border:1px solid #263042; border-radius:12px; padding:14px; text-align:center; }
        .til-kpi .v { font-size: 1.6rem; font-weight: 900; color: #F8FAFC; }
        .til-kpi .l { font-size: 0.75rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em; }
        </style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
