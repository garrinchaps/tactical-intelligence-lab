"""Laboratório — simulador de cenários por bootstrap (EmpiricalFallback) e demonstração de homografia."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.canonical.provenance import ProvenanceRecord, ProvenanceRegistry
from src.connectors.empirical_fallback import CI_TEXT, GENERATOR, METRICS, MINUTE_BANDS, SCORE_CTX, EmpiricalFallback
from src.ingestion.video_homography_demo import PitchHomographyProjector
from src.ui import charts
from src.ui.components import comparison_table, empty_state, error_state, metric_card, note, page_header, provenance_panel
from src.ui.context import get_service

DB = "database/tactical_lab.db"


@st.cache_resource(show_spinner=False)
def _fallback():
    fb = EmpiricalFallback.from_cache(db_path=DB)
    if fb is not None:
        return fb
    svc = get_service()
    cat = svc.db.catalog("data_level = 'EVENTS' AND data_source = 'statsbomb'", limit=40)
    if cat.empty:
        return None
    home = {int(r.match_id): r.home_team_name for r in cat.itertuples()}
    pool = EmpiricalFallback.build_pool(list(home), svc.db.load_events, lambda m: home.get(m, ""))
    return EmpiricalFallback(pool, db_path=DB) if not pool.empty else None


def _scenarios(reg: ProvenanceRegistry) -> None:
    st.markdown("### 🎲 Simulador de cenários (bootstrap empírico)")
    note("O que é", f"Reamostragem com reposição (B = 100) de ações REAIS do StatsBomb no banco local, estratificada por "
         f"zona × placar × faixa de minuto. Todo valor sai com tier SIMULADO e {CI_TEXT}: mede a incerteza do gerador, "
         "não a de um jogo real.", "warn")
    with st.spinner("Carregando a distribuição empírica de referência..."):
        try:
            fb = _fallback()
        except Exception as exc:
            error_state("Não foi possível montar a distribuição de referência", exc)
            return
    if fb is None:
        empty_state("Sem partidas reais com eventos no banco", "", "🎲", "Abra a final da Copa 2022 ou sincronize o StatsBomb.")
        return
    a, b, c, d = st.columns(4)
    metric = a.selectbox("Métrica", list(METRICS), format_func=lambda k: METRICS[k]["label"])
    score = b.selectbox("Placar da equipe", ["todos", *SCORE_CTX])
    band = c.selectbox("Faixa de minuto", ["todas", *MINUTE_BANDS])
    B = d.select_slider("Réplicas (B)", [50, 100, 200], value=100)
    grid = fb.zone_grid(metric, None if score == "todos" else score, None if band == "todas" else band, B=B)
    ok = grid[grid["status"] == "ok"]
    n_matches = int(fb.pool["match_id"].nunique())
    tot = fb.estimate(metric, None, None if score == "todos" else score, None if band == "todas" else band, B=B, persist=False)
    rec = reg.register(ProvenanceRecord(
        "sim_total", METRICS[metric]["label"], tot["value"], f"Distribuição empírica StatsBomb Open Data ({n_matches} partidas)",
        "EmpiricalFallback", "Derivado de StatsBomb Open Data — crédito à StatsBomb", "SIMULATED",
        f"bootstrap estratificado, n = {tot['n']}", generator=f"{GENERATOR} (B={B})", ci_low=tot["ci_low"], ci_high=tot["ci_high"]))
    k = st.columns([1, 2])
    with k[0]:
        if tot["value"] is None:
            metric_card(METRICS[metric]["label"], "—", rec, tot["status"], "neg")
        else:
            metric_card(METRICS[metric]["label"] + " — campo inteiro", f"{tot['value']:g}", rec,
                        f"IC 95% {tot['ci_low']:g}–{tot['ci_high']:g} · n = {tot['n']}", "neu", unit=METRICS[metric]["unit"])
    with k[1]:
        if ok.empty:
            empty_state("Todas as zonas com amostra insuficiente neste recorte (n < 30).", icon="🧮")
        else:
            st.plotly_chart(charts.ci_bars(grid, f"{METRICS[metric]['label']} por zona — {CI_TEXT}", METRICS[metric]["unit"]),
                            use_container_width=True)
    comparison_table(grid[["zone", "value", "ci_low", "ci_high", "n", "status"]].rename(
        columns={"zone": "zona", "value": "valor", "ci_low": "IC 2,5%", "ci_high": "IC 97,5%"}),
        f"Gerador {GENERATOR}; {n_matches} partidas de referência; zonas com n < 30 ficam sem valor.")


def _homography(reg: ProvenanceRegistry) -> None:
    st.markdown("### 🎥 Visão computacional — homografia imagem → campo 2D")
    note("Demonstração com frame SINTÉTICO", "Projeção homográfica (DLT via SVD) de posições na imagem para o campo. "
         "Base para o roadmap de detecção (YOLO) e rastreamento (ByteTrack); não processa vídeo real.")
    try:
        demo = PitchHomographyProjector.run_synthetic_broadcast_frame_demo()
    except Exception as exc:
        error_state("Demonstração indisponível", exc)
        return
    cm = demo["compactness_metrics"]

    def p(key, label, value):
        return reg.register(ProvenanceRecord(key, label, value, "Frame sintético gerado no laboratório", "PitchHomographyProjector",
                                             "—", "SIMULATED", "homografia DLT/SVD sobre pontos sintéticos",
                                             generator="run_synthetic_broadcast_frame_demo"))
    c = st.columns(4)
    with c[0]:
        metric_card("Altura da linha defensiva", cm["defensive_line_height_m"], p("h1", "Altura da linha", cm["defensive_line_height_m"]), unit=" m")
    with c[1]:
        v = cm["inter_line_distance_def_to_mid_m"]
        metric_card("Distância defesa–meio", v, p("h2", "Distância entre linhas", v), cm["compactness_diagnosis"],
                    "pos" if v <= 14.5 else "neg", unit=" m")
    with c[2]:
        metric_card("Maior espaço entre defensores", cm["max_horizontal_defender_gap_m"],
                    p("h3", "Maior espaço", cm["max_horizontal_defender_gap_m"]), f"média {cm['avg_horizontal_defender_gap_m']} m", unit=" m")
    with c[3]:
        metric_card("Polígono convexo", cm["convex_hull_area_m2"], p("h4", "Área convexa", cm["convex_hull_area_m2"]),
                    f"{cm['players_detected_in_frame']} atletas", unit=" m²")
    comparison_table(demo["projected_players_df"])


def render(_ctx=None) -> None:
    page_header("🧪 Laboratório", "Simulador de cenários com incerteza declarada e demonstração de visão computacional.")
    reg = ProvenanceRegistry()
    t1, t2 = st.tabs(["🎲 Simulador de cenários", "🎥 Homografia"])
    with t1:
        _scenarios(reg)
    with t2:
        _homography(reg)
    provenance_panel(reg)
