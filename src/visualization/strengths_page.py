"""
Página 6 do app: Pontos Fortes e Fracos (estilo Football Manager Data Hub).

Separada do app.py para manter o arquivo principal enxuto. Recebe os dados já
carregados pela sessão e desenha: seletor atleta/equipe, cartões de contexto,
tabela lado a lado (acima x abaixo da média), radar de percentis e a
interpretação textual auditada.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.intelligence.llm_analyst import GenerativeTacticalAnalyst
from src.metrics.strengths_weaknesses import (
    STRENGTH_PERCENTILE,
    WEAKNESS_PERCENTILE,
    ReferenceBaselineBuilder,
    StrengthsWeaknessesEngine,
)


@st.cache_data(show_spinner=False)
def _cached_baselines(_load_events_fn: Callable, cache_key: str) -> Dict[str, Any]:
    return ReferenceBaselineBuilder.load_or_build(_load_events_fn)


def _items_to_df(items: List[Dict[str, Any]]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame(columns=["Métrica", "Valor", "Mediana ref.", "Percentil"])
    return pd.DataFrame(
        [
            {
                "Métrica": d["label"],
                "Valor": d["value"],
                "Mediana ref.": d["reference_median"],
                "Percentil": d["percentile"],
            }
            for d in items
        ]
    )


def _radar(analysis: Dict[str, Any]) -> go.Figure:
    items = analysis["strengths"] + analysis["neutral"] + analysis["weaknesses"]
    labels = [d["label"] for d in items]
    values = [d["percentile"] for d in items]
    fig = go.Figure()
    if labels:
        fig.add_trace(
            go.Scatterpolar(
                r=values + values[:1],
                theta=labels + labels[:1],
                fill="toself",
                name=analysis["entity"],
                line=dict(color="#00FF7F", width=2),
                fillcolor="rgba(0,255,127,0.18)",
            )
        )
        fig.add_trace(
            go.Scatterpolar(
                r=[50] * (len(labels) + 1),
                theta=labels + labels[:1],
                name="Mediana da referência (P50)",
                line=dict(color="#94A3B8", dash="dot", width=1),
            )
        )
    fig.update_layout(
        polar=dict(
            bgcolor="#0F172A",
            radialaxis=dict(range=[0, 100], tickvals=[30, 50, 70, 100], color="#94A3B8"),
            angularaxis=dict(color="#E2E8F0"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0"),
        legend=dict(orientation="h", y=-0.12),
        margin=dict(l=40, r=40, t=30, b=30),
        height=470,
    )
    return fig


def render_strengths_weaknesses_page(
    df_events: pd.DataFrame,
    df_chains: pd.DataFrame,
    target_team: str,
    current_match_id: int,
    is_sim_mode: bool,
    load_events_fn: Callable,
) -> None:
    st.subheader("⚖️ Pontos Fortes e Fracos — Comparativo Contextual (estilo FM Data Hub)")
    st.caption(
        f"Percentil contextual: ≥ {STRENGTH_PERCENTILE:.0f} = ponto forte · ≤ {WEAKNESS_PERCENTILE:.0f} = ponto fraco. "
        "Atletas são comparados com a mesma função (métricas por 90 min); equipes com todas as equipes da base. "
        "A referência usa apenas partidas reais do StatsBomb Open Data salvas no banco local."
    )

    c_mode, c_entity, c_ai = st.columns([0.9, 2.0, 1.1])
    with c_mode:
        mode = st.radio("Analisar:", ["Atleta", "Equipe"], horizontal=True)
    with c_entity:
        if mode == "Atleta":
            players = (
                df_events.loc[df_events["team_name"].notna(), ["player_name", "team_name"]]
                .dropna()
                .drop_duplicates()
            )
            options = [f"{r.player_name} — {r.team_name}" for r in players.itertuples()]
            default_idx = next(
                (i for i, o in enumerate(options) if o.endswith(f"— {target_team}")), 0
            )
            chosen = st.selectbox("Atleta:", options, index=default_idx) if options else None
            entity = chosen.split(" — ")[0] if chosen else None
        else:
            teams = df_events["team_name"].dropna().unique().tolist()
            entity = st.selectbox(
                "Equipe:", teams, index=teams.index(target_team) if target_team in teams else 0
            )
    with c_ai:
        use_llm = st.checkbox("Interpretação com Gemini (auditada)", value=False)

    if not entity:
        st.info("Nenhum atleta disponível nesta partida.")
        return

    try:
        with st.spinner("Carregando base de referência (na primeira vez leva ~20 s)..."):
            match_ids = ReferenceBaselineBuilder.available_real_match_ids()
            baselines = _cached_baselines(load_events_fn, ",".join(map(str, match_ids)))
    except Exception as exc:
        st.warning(f"Não foi possível montar a base de referência: {exc}")
        return

    if not baselines.get("match_ids"):
        st.warning(
            "A base de referência está vazia: carregue algumas partidas reais do StatsBomb "
            "(aba Match Center) para que elas sejam salvas no banco local."
        )
        return

    try:
        if mode == "Atleta":
            analysis = StrengthsWeaknessesEngine.analyze_player(
                df_events, entity, baselines, exclude_match_id=int(current_match_id)
            )
        else:
            analysis = StrengthsWeaknessesEngine.analyze_team(
                df_events, df_chains, entity, baselines, exclude_match_id=int(current_match_id)
            )
    except Exception as exc:
        st.warning(f"Não foi possível comparar '{entity}': {exc}")
        return

    # Cartões de contexto
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Grupo comparado", analysis["comparison_scope"].capitalize())
    k2.metric(
        "Amostra de referência",
        analysis.get("reference_players_n", analysis.get("reference_teams_n", 0)),
    )
    k3.metric("Partidas na referência", analysis["reference_matches_n"])
    k4.metric("Grau de evidência", analysis["evidence_grade"])

    col_s, col_w = st.columns(2)
    with col_s:
        st.markdown("#### 🟢 Pontos Fortes (acima da média)")
        st.dataframe(_items_to_df(analysis["strengths"]), use_container_width=True, hide_index=True)
    with col_w:
        st.markdown("#### 🔴 Pontos Fracos (abaixo da média)")
        st.dataframe(_items_to_df(analysis["weaknesses"]), use_container_width=True, hide_index=True)

    col_r, col_t = st.columns([1.1, 1.0])
    with col_r:
        st.plotly_chart(_radar(analysis), use_container_width=True)
    with col_t:
        st.markdown("#### 🧠 Interpretação")
        res = GenerativeTacticalAnalyst().interpret_strengths_weaknesses(
            analysis, is_simulation=is_sim_mode, prefer_llm=use_llm
        )
        st.caption(f"Motor: {res['engine_used']}")
        blocked = res["hallucination_audit"].get("blocked_llm_audit")
        if blocked:
            st.warning("🛡️ O texto da IA foi bloqueado pelo guardião e substituído pelo texto local.")
        st.markdown(res["report_markdown"])

    with st.expander("Métricas dentro da faixa normal (percentil 30–70)"):
        st.dataframe(_items_to_df(analysis["neutral"]), use_container_width=True, hide_index=True)
