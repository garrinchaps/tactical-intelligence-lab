"""
Módulo Experimental de Visão Computacional e Homografia Planar (Camada 4 - Entrada 3)
Converte coordenadas de pixels (u, v) de frames de vídeo de transmissão (câmera aberta)
em coordenadas táticas (x, y) no padrão 120x80 jardas utilizando Direct Linear Transform (SVD).
Calcula compactação de linhas e distâncias entre setores a partir de frames de vídeo.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from src.geometry.pitch_zones import PitchGeometry


class PitchHomographyProjector:
    """
    Solucionador matemático de Homografia 2D via Decomposição em Valores Singulares (SVD).
    Não exige GPU nem compilação externa pesada: opera em NumPy puro e suporta
    integração direta com bounding boxes de detectores (YOLOv8 / OpenCV).
    """

    def __init__(
        self,
        src_pixel_points: np.ndarray,
        dst_pitch_points: np.ndarray,
    ) -> None:
        """
        Inicializa e estima a matriz de homografia H (3x3) a partir de pelo menos
        4 pares de pontos correspondentes:
        - src_pixel_points: shape (N, 2) em pixels (u, v) da imagem/vídeo.
        - dst_pitch_points: shape (N, 2) em jardas (x, y) do campo StatsBomb (120x80).
        """
        self.H = self.compute_homography_svd(src_pixel_points, dst_pitch_points)

    @staticmethod
    def compute_homography_svd(
        src_pts: np.ndarray, dst_pts: np.ndarray
    ) -> np.ndarray:
        """
        Resolve o sistema Ah = 0 via Direct Linear Transform (DLT) e SVD para encontrar
        a matriz projetiva H (3x3) que leva (u, v) -> (x, y).
        """
        src = np.asarray(src_pts, dtype=float)
        dst = np.asarray(dst_pts, dtype=float)
        if src.shape[0] < 4 or dst.shape[0] < 4 or src.shape != dst.shape:
            raise ValueError(
                "São necessários pelo menos 4 pontos não-colineares correspondentes para calcular a Homografia."
            )

        A = []
        for (u, v), (x, y) in zip(src, dst):
            A.append([-u, -v, -1.0, 0.0, 0.0, 0.0, u * x, v * x, x])
            A.append([0.0, 0.0, 0.0, -u, -v, -1.0, u * y, v * y, y])

        A_mat = np.asarray(A, dtype=float)
        _, _, Vt = np.linalg.svd(A_mat)
        H = Vt[-1].reshape(3, 3)
        if abs(H[2, 2]) > 1e-12:
            H = H / H[2, 2]
        return H

    def pixel_to_pitch(self, u: float, v: float) -> Tuple[float, float]:
        """
        Converte a coordenada do pé do jogador no vídeo (u, v em pixels)
        para a coordenada real no campo (x, y em jardas 120x80).
        """
        vec = np.array([float(u), float(v), 1.0], dtype=float)
        projected = self.H @ vec
        w = projected[2] if abs(projected[2]) > 1e-9 else 1e-9
        x_pitch = float(np.clip(projected[0] / w, 0.0, 120.0))
        y_pitch = float(np.clip(projected[1] / w, 0.0, 80.0))
        return round(x_pitch, 2), round(y_pitch, 2)

    def project_detections_dataframe(self, df_detections: pd.DataFrame) -> pd.DataFrame:
        """
        Recebe um DataFrame com detecções de vídeo (colunas: player_id, team, pixel_u, pixel_v)
        e adiciona as coordenadas (x, y) projetadas no campo 120x80 e o corredor tático.
        """
        out = df_detections.copy()
        xs, ys = [], []
        for _, row in out.iterrows():
            px, py = self.pixel_to_pitch(row["pixel_u"], row["pixel_v"])
            xs.append(px)
            ys.append(py)

        out["x"] = xs
        out["y"] = ys
        out["tactical_third"] = PitchGeometry.get_pitch_third_series(out["x"])
        out["tactical_corridor"] = PitchGeometry.get_vertical_corridor_series(out["y"])
        return out

    @classmethod
    def analyze_frame_tactical_compactness(
        cls, df_projected: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        A partir das coordenadas (x, y) projetadas de todos os jogadores visíveis no frame,
        calcula métricas exclusivas de rastreamento espacial (Tracking / Vídeo):
        - Polígono Convexo (Convex Hull) instantâneo da equipe.
        - Altura da Linha Defensiva (média X dos 4 jogadores de linha mais recuados).
        - Profundidade Total do Bloco (distância longitudinal em metros entre o defensor mais recuado e o atacante mais avançado).
        - Distância entre Linha Defensiva e Linha de Meio-Campo (Compactação Entrelinhas em metros).
        """
        team_df = df_projected[df_projected["team_name"] == target_team].copy()
        if len(team_df) < 4:
            return {"team_name": target_team, "status": "INSUFFICIENT_PLAYERS_IN_FRAME"}

        team_df = team_df.sort_values("x").reset_index(drop=True)

        # Descarta goleiro se houver um jogador muito próximo à linha de gol (x < 12) e >= 8 atletas no frame
        outfield = team_df.iloc[1:].copy() if (len(team_df) >= 8 and team_df.iloc[0]["x"] < 14.0) else team_df.copy()

        # Divide os jogadores de linha em Linha Defensiva (primeiros 4) e Linha Média (próximos 3-4)
        def_line = outfield.iloc[: min(4, len(outfield))]
        mid_line = outfield.iloc[min(4, len(outfield)) : min(8, len(outfield))]

        def_line_height_m = round(
            float(def_line["x"].mean()) * PitchGeometry.YARD_TO_METER, 2
        )
        mid_line_height_m = (
            round(float(mid_line["x"].mean()) * PitchGeometry.YARD_TO_METER, 2)
            if not mid_line.empty
            else def_line_height_m + 12.0
        )
        inter_line_distance_m = round(abs(mid_line_height_m - def_line_height_m), 2)

        block_depth_m = round(
            float(outfield["x"].max() - outfield["x"].min())
            * PitchGeometry.YARD_TO_METER,
            2,
        )
        block_width_m = round(
            float(outfield["y"].max() - outfield["y"].min())
            * PitchGeometry.YARD_TO_METER,
            2,
        )

        # Distância lateral média entre defensores adjacentes na linha de trás
        def_sorted_y = def_line.sort_values("y")
        if len(def_sorted_y) >= 2:
            gaps_y_m = (
                np.diff(def_sorted_y["y"].to_numpy()) * PitchGeometry.YARD_TO_METER
            )
            max_defensive_gap_m = round(float(np.max(gaps_y_m)), 2)
            avg_defensive_gap_m = round(float(np.mean(gaps_y_m)), 2)
        else:
            max_defensive_gap_m, avg_defensive_gap_m = 0.0, 0.0

        hull = PitchGeometry.compute_team_convex_hull(
            outfield, trim_outliers_pct=0.0
        )

        return {
            "team_name": target_team,
            "status": "OK",
            "players_detected_in_frame": int(len(team_df)),
            "defensive_line_height_m": def_line_height_m,
            "midfield_line_height_m": mid_line_height_m,
            "inter_line_distance_def_to_mid_m": inter_line_distance_m,
            "total_block_depth_length_m": block_depth_m,
            "total_block_width_m": block_width_m,
            "avg_horizontal_defender_gap_m": avg_defensive_gap_m,
            "max_horizontal_defender_gap_m": max_defensive_gap_m,
            "convex_hull_area_m2": hull["hull_area_m2"],
            "compactness_diagnosis": (
                "Bloco Compacto Ideal (< 14m entrelinhas)"
                if inter_line_distance_m <= 14.5
                else "Alerta de Espaço Entrelinhas Exposto (> 14.5m entre Defesa e Meio)"
            ),
        }

    @classmethod
    def run_synthetic_broadcast_frame_demo(cls) -> Dict[str, Any]:
        """
        Executa uma demonstração completa de calibração de câmera Full HD (1920x1080)
        para o gramado 120x80 e projeta os 20 jogadores de linha detectados no frame.
        """
        # 4 pontos conhecidos no frame de uma câmera de TV central (Full HD 1920x1080)
        # correspondentes às interseções da linha central e da grande área direita
        src_pixels = np.array(
            [
                [420.0, 180.0],   # Interseção superior da linha de meio-campo (x=60, y=0)
                [260.0, 920.0],   # Interseção inferior da linha de meio-campo (x=60, y=80)
                [1480.0, 290.0],  # Quina superior da grande área ofensiva (x=102, y=18)
                [1620.0, 790.0],  # Quina inferior da grande área ofensiva (x=102, y=62)
            ]
        )
        dst_pitch = np.array(
            [
                [60.0, 0.0],
                [60.0, 80.0],
                [102.0, 18.0],
                [102.0, 62.0],
            ]
        )

        projector = cls(src_pixels, dst_pitch)

        # Simula bounding boxes (pés dos jogadores u, v) de uma equipe defendendo em 4-4-2
        detections = [
            {"player_id": "LD", "team_name": "Bloco Defensivo", "pixel_u": 1290, "pixel_v": 310},
            {"player_id": "ZAG_D", "team_name": "Bloco Defensivo", "pixel_u": 1320, "pixel_v": 430},
            {"player_id": "ZAG_E", "team_name": "Bloco Defensivo", "pixel_u": 1350, "pixel_v": 580},
            {"player_id": "LE", "team_name": "Bloco Defensivo", "pixel_u": 1380, "pixel_v": 720},
            {"player_id": "MD", "team_name": "Bloco Defensivo", "pixel_u": 1060, "pixel_v": 330},
            {"player_id": "VOL_1", "team_name": "Bloco Defensivo", "pixel_u": 1090, "pixel_v": 460},
            {"player_id": "VOL_2", "team_name": "Bloco Defensivo", "pixel_u": 1110, "pixel_v": 570},
            {"player_id": "ME", "team_name": "Bloco Defensivo", "pixel_u": 1140, "pixel_v": 700},
            {"player_id": "ATA_1", "team_name": "Bloco Defensivo", "pixel_u": 820, "pixel_v": 450},
            {"player_id": "ATA_2", "team_name": "Bloco Defensivo", "pixel_u": 840, "pixel_v": 560},
        ]
        df_det = pd.DataFrame(detections)
        df_proj = projector.project_detections_dataframe(df_det)
        metrics = cls.analyze_frame_tactical_compactness(df_proj, "Bloco Defensivo")

        return {
            "homography_matrix": projector.H.round(6).tolist(),
            "projected_players_df": df_proj,
            "compactness_metrics": metrics,
        }


if __name__ == "__main__":
    print("=" * 80)
    print("TACTICAL INTELLIGENCE LAB - HOMOGRAFIA DE VÍDEO E COMPACTAÇÃO 2D (DIA 12)")
    print("=" * 80)

    demo = PitchHomographyProjector.run_synthetic_broadcast_frame_demo()
    m = demo["compactness_metrics"]
    print("\n[1/2] Matriz de Homografia Planar 3x3 Calculada via SVD:")
    print(np.array(demo["homography_matrix"]))

    print("\n[2/2] Diagnóstico Geométrico do Frame de Vídeo (Compactação das Linhas):")
    print(f"  * Jogadores Projetados no Frame: {m['players_detected_in_frame']}")
    print(f"  * Altura da Linha Defensiva: {m['defensive_line_height_m']} m")
    print(f"  * Distância Entrelinhas (Defesa <-> Meio-Campo): {m['inter_line_distance_def_to_mid_m']} m")
    print(f"  * Profundidade Total do Bloco: {m['total_block_depth_length_m']} m | Largura: {m['total_block_width_m']} m")
    print(f"  * Maior Abertura Horizontal entre Defensores: {m['max_horizontal_defender_gap_m']} m")
    print(f"  * Área do Polígono Convexo (Convex Hull): {m['convex_hull_area_m2']} m²")
    print(f"  * Diagnóstico Estrutural: {m['compactness_diagnosis']}")