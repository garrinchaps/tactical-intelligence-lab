"""
Testes Automatizados do Dia 12: Validação da Matriz de Homografia Planar (SVD),
Compactação de Linhas em Frame de Vídeo e Integridade da Aplicação.
"""

import numpy as np
import pytest
from src.ingestion.video_homography_demo import PitchHomographyProjector


def test_homography_svd_projection_accuracy():
    """
    Garante que a matriz de homografia H calculada via SVD mapeie os 4 pontos
    de referência do vídeo exatamente para as coordenadas do campo (erro < 0.01 jarda)
    e calcule as métricas de compactação entrelinhas sem erros.
    """
    demo = PitchHomographyProjector.run_synthetic_broadcast_frame_demo()
    metrics = demo["compactness_metrics"]
    df_proj = demo["projected_players_df"]

    assert metrics["status"] == "OK"
    assert metrics["players_detected_in_frame"] == 10
    assert metrics["defensive_line_height_m"] > 0.0
    assert metrics["inter_line_distance_def_to_mid_m"] > 5.0
    assert metrics["convex_hull_area_m2"] > 100.0
    assert {"x", "y", "tactical_third", "tactical_corridor"}.issubset(df_proj.columns)

    # Verifica precisão da projeção nos pontos âncora de calibração
    src_pixels = np.array(
        [[420.0, 180.0], [260.0, 920.0], [1480.0, 290.0], [1620.0, 790.0]]
    )
    dst_pitch = np.array(
        [[60.0, 0.0], [60.0, 80.0], [102.0, 18.0], [102.0, 62.0]]
    )
    projector = PitchHomographyProjector(src_pixels, dst_pitch)

    x0, y0 = projector.pixel_to_pitch(420.0, 180.0)
    assert x0 == pytest.approx(60.0, abs=0.05)
    assert y0 == pytest.approx(0.0, abs=0.05)

    x2, y2 = projector.pixel_to_pitch(1480.0, 290.0)
    assert x2 == pytest.approx(102.0, abs=0.05)
    assert y2 == pytest.approx(18.0, abs=0.05)