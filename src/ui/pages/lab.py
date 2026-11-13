"""Seção 🎥 Laboratório — demonstração de visão computacional (homografia vídeo → campo 2D)."""

from __future__ import annotations

import streamlit as st

from src.ingestion.video_homography_demo import PitchHomographyProjector
from src.ui.components import metric_card, section_header


def render(_ctx=None) -> None:
    section_header("🎥 Laboratório de visão computacional",
                   "Demonstração com um frame SINTÉTICO: projeção homográfica (SVD) de posições da imagem para o campo 2D. "
                   "Base para o roadmap de YOLO + ByteTrack.")
    try:
        demo = PitchHomographyProjector.run_synthetic_broadcast_frame_demo()
        cm = demo["compactness_metrics"]
        c = st.columns(4)
        with c[0]:
            metric_card("Altura da linha defensiva", f"{cm['defensive_line_height_m']} m", "frame projetado")
        with c[1]:
            metric_card("Distância defesa–meio", f"{cm['inter_line_distance_def_to_mid_m']} m", cm["compactness_diagnosis"],
                        "pos" if cm["inter_line_distance_def_to_mid_m"] <= 14.5 else "neg")
        with c[2]:
            metric_card("Maior espaço entre defensores", f"{cm['max_horizontal_defender_gap_m']} m",
                        f"média {cm['avg_horizontal_defender_gap_m']} m")
        with c[3]:
            metric_card("Polígono convexo", f"{cm['convex_hull_area_m2']} m²", f"{cm['players_detected_in_frame']} atletas")
        st.dataframe(demo["projected_players_df"], use_container_width=True, hide_index=True)
    except Exception as exc:
        st.warning(f"Demonstração indisponível: {exc}")
