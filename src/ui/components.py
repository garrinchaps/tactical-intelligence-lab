"""Componentes visuais reutilizáveis."""

from __future__ import annotations

from typing import Optional

import numpy as np
import streamlit as st

from src.data_hub.registry import BADGES, COLORS, LEVEL_DESCRIPTIONS


def section_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="til-section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="til-section-sub">{subtitle}</div>', unsafe_allow_html=True)


def empty_state(message: str) -> None:
    st.markdown(f'<div class="til-empty">{message}</div>', unsafe_allow_html=True)


def level_badge(level: str) -> str:
    color = COLORS.get(level, "#94A3B8")
    return f'<span class="til-level-badge" style="color:{color};">{BADGES.get(level, level)}</span>'


def level_banner(level: str, source_label: str = "") -> None:
    """Faixa com o nível de dado da partida, sempre visível no topo."""
    color = COLORS.get(level, "#94A3B8")
    bg = {"#F59E0B": "#3B1D00"}.get(color, "#111827")
    st.markdown(
        f"""
        <div style="background:{bg}; border:1px solid {color}; border-left:5px solid {color}; border-radius:10px;
                    padding:10px 16px; margin:4px 0 12px 0;">
            <div style="color:{color}; font-weight:900; font-size:0.95rem;">{BADGES.get(level, level)}
                <span style="color:#94A3B8; font-weight:600; font-size:0.8rem;">&nbsp;• fonte: {source_label}</span></div>
            <div style="color:#CBD5E1; font-size:0.84rem; margin-top:3px;">{LEVEL_DESCRIPTIONS.get(level, '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, badge_text: str = "", status: str = "neu") -> None:
    badge_class = {"pos": "metric-badge-pos", "neg": "metric-badge-neg"}.get(status, "metric-badge-neu")
    badge = f'<span class="{badge_class}">{badge_text}</span>' if badge_text else ""
    st.markdown(
        f'<div class="til-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>{badge}</div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, value: str) -> None:
    st.markdown(f'<div class="til-kpi"><div class="v">{value}</div><div class="l">{label}</div></div>',
                unsafe_allow_html=True)


def stat_pill(title: str, left_val: Optional[float], right_val: Optional[float], left_display: str,
              right_display: str, invert_advantage: bool = False) -> None:
    lv, rv = float(left_val or 0), float(right_val or 0)
    total = max(lv + rv, 1e-6)
    left_pct = float(np.clip((lv / total) * 100.0, 5.0, 95.0)) if (lv + rv) > 0 else 50.0
    if invert_advantage:
        left_pct = 100.0 - left_pct
    st.markdown(
        f"""
        <div class="pill-bar-container">
            <div class="pill-bar-header">
                <span style="color:#00FF7F;">{left_display}</span>
                <span style="color:#94A3B8; font-weight:600;">{title}</span>
                <span style="color:#38BDF8;">{right_display}</span>
            </div>
            <div class="pill-bar-track">
                <div class="pill-bar-fill-left" style="width: {left_pct:.1f}%;"></div>
                <div class="pill-bar-fill-right" style="width: {100 - left_pct:.1f}%;"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def scoreboard(home: str, away: str, score: str, subtitle_html: str = "", badge_html: str = "") -> None:
    st.markdown(
        f"""
        <div class="sofascore-banner">
            {badge_html}
            <div class="sofascore-teams-row">
                <div class="sofascore-team-name" style="text-align:right;">{home}</div>
                <div class="sofascore-score-box">{score}</div>
                <div class="sofascore-team-name" style="text-align:left;">{away}</div>
            </div>
            <div style="margin-top:10px; color:#94A3B8; font-size:0.85rem;">{subtitle_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
