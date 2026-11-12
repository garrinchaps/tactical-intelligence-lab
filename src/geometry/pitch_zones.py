"""
Módulo de Geometria Tática do Campo (Camada 2 - Geometria Espacial)
Converte coordenadas (x, y) no padrão 120x80 jardas em conceitos posicionais:
Terços, 5 Corredores Posicionais, Grade de 18 Zonas (Zona 14), Distância ao Gol e Convex Hull.
"""

from typing import Dict
import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint


class PitchGeometry:
    """
    Motor geométrico determinístico para análise espacial de futebol.
    Dimensões padrão StatsBomb: Comprimento X in [0, 120], Largura Y in [0, 80].
    Origem (0, 0) = Canto superior esquerdo (defensivo esquerdo).
    Centro do gol adversário = (120.0, 40.0).
    Fator de conversão: 1 jarda = 0.9144 metros.
    """

    PITCH_LENGTH: float = 120.0
    PITCH_WIDTH: float = 80.0
    GOAL_X: float = 120.0
    GOAL_Y: float = 40.0
    YARD_TO_METER: float = 0.9144

    # Limites da Grande Área Ofensiva (Penalty Box) no padrão 120x80
    PENALTY_BOX_X_MIN: float = 102.0
    PENALTY_BOX_Y_MIN: float = 18.0
    PENALTY_BOX_Y_MAX: float = 62.0

    @classmethod
    def get_pitch_third_series(cls, x: pd.Series) -> pd.Series:
        """
        Classifica a coordenada X nos 3 terços clássicos do campo:
        - Terço Defensivo: 0 <= x < 40
        - Terço Médio: 40 <= x < 80
        - Terço Ofensivo (Final): 80 <= x <= 120
        """
        x_num = pd.to_numeric(x, errors="coerce").astype(float)
        conditions = [
            (x_num >= 0.0) & (x_num < 40.0),
            (x_num >= 40.0) & (x_num < 80.0),
            (x_num >= 80.0) & (x_num <= 125.0),
        ]
        choices = ["Terço Defensivo", "Terço Médio", "Terço Ofensivo"]
        return pd.Series(
            np.select(conditions, choices, default="Indefinido"), index=x.index
        )

    @classmethod
    def get_vertical_corridor_series(cls, y: pd.Series) -> pd.Series:
        """
        Classifica a coordenada Y nos 5 corredores verticais do Jogo Posicional:
        - Corredor Lateral Esquerdo: 0 <= y < 18
        - Meio-Espaço Esquerdo (Left Half-Space): 18 <= y < 30
        - Corredor Central: 30 <= y <= 50
        - Meio-Espaço Direito (Right Half-Space): 50 < y <= 62
        - Corredor Lateral Direito: 62 < y <= 80
        """
        y_num = pd.to_numeric(y, errors="coerce").astype(float)
        conditions = [
            (y_num >= -5.0) & (y_num < 18.0),
            (y_num >= 18.0) & (y_num < 30.0),
            (y_num >= 30.0) & (y_num <= 50.0),
            (y_num > 50.0) & (y_num <= 62.0),
            (y_num > 62.0) & (y_num <= 85.0),
        ]
        choices = [
            "Corredor Lateral Esquerdo",
            "Meio-Espaço Esquerdo",
            "Corredor Central",
            "Meio-Espaço Direito",
            "Corredor Lateral Direito",
        ]
        return pd.Series(
            np.select(conditions, choices, default="Indefinido"), index=y.index
        )

    @classmethod
    def get_zone_18_series(cls, x: pd.Series, y: pd.Series) -> pd.Series:
        """
        Mapeia (x, y) na grade tática de 18 Zonas (6 faixas em X por 3 faixas em Y).
        """
        x_num = pd.to_numeric(x, errors="coerce").astype(float)
        y_num = pd.to_numeric(y, errors="coerce").astype(float)
        valid = x_num.notna() & y_num.notna()

        col_idx = np.clip(np.floor(x_num.fillna(0.0) / 20.0), 0, 5).astype(int)

        row_idx = np.select(
            [
                y_num.fillna(0.0) < 26.67,
                (y_num.fillna(0.0) >= 26.67) & (y_num.fillna(0.0) <= 53.33),
                y_num.fillna(0.0) > 53.33,
            ],
            [1, 2, 3],
            default=2,
        )

        zone_num = (col_idx * 3) + row_idx
        result = pd.Series(zone_num, index=x.index, dtype="Int64")
        result[~valid] = pd.NA
        return result

    @classmethod
    def is_zone_14_series(cls, x: pd.Series, y: pd.Series) -> pd.Series:
        """
        Identifica a Zona 14 (frontal à grande área): 80 <= x < 102 e 26.67 <= y <= 53.33.
        """
        x_num = pd.to_numeric(x, errors="coerce").astype(float)
        y_num = pd.to_numeric(y, errors="coerce").astype(float)
        cond = (x_num >= 80.0) & (x_num < 102.0) & (y_num >= 26.67) & (y_num <= 53.33)
        return cond.fillna(False).astype(int)

    @classmethod
    def is_offensive_half_space_series(cls, x: pd.Series, y: pd.Series) -> pd.Series:
        """
        Identifica ações nos Meios-Espaços Ofensivos: x >= 80 e y em [18, 30) ou (50, 62].
        """
        x_num = pd.to_numeric(x, errors="coerce").astype(float)
        y_num = pd.to_numeric(y, errors="coerce").astype(float)
        in_x = x_num >= 80.0
        in_y = ((y_num >= 18.0) & (y_num < 30.0)) | ((y_num > 50.0) & (y_num <= 62.0))
        return (in_x & in_y).fillna(False).astype(int)

    @classmethod
    def is_penalty_box_series(cls, x: pd.Series, y: pd.Series) -> pd.Series:
        """Verifica se a coordenada está dentro da Grande Área adversária."""
        x_num = pd.to_numeric(x, errors="coerce").astype(float)
        y_num = pd.to_numeric(y, errors="coerce").astype(float)
        cond = (
            (x_num >= cls.PENALTY_BOX_X_MIN)
            & (y_num >= cls.PENALTY_BOX_Y_MIN)
            & (y_num <= cls.PENALTY_BOX_Y_MAX)
        )
        return cond.fillna(False).astype(int)

    @classmethod
    def distance_to_goal_yards(cls, x: pd.Series, y: pd.Series) -> pd.Series:
        """Calcula a distância euclidiana (em jardas) até o centro do gol adversário (120, 40)."""
        x_num = pd.to_numeric(x, errors="coerce").astype(float)
        y_num = pd.to_numeric(y, errors="coerce").astype(float)
        return np.sqrt((cls.GOAL_X - x_num) ** 2 + (cls.GOAL_Y - y_num) ** 2)

    @classmethod
    def enrich_spatial_features(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Recebe um DataFrame de eventos com (x, y, end_x, end_y), força tipagem float64
        segura e adiciona todas as colunas geométricas e vetores de progressão.
        """
        out = df.copy()

        # Garante que coordenadas sejam sempre float64 (mesmo quando vierem como None/object)
        for coord_col in ["x", "y", "end_x", "end_y"]:
            if coord_col in out.columns:
                out[coord_col] = pd.to_numeric(out[coord_col], errors="coerce").astype(float)
            else:
                out[coord_col] = np.nan

        # 1. Classificação da origem (x, y)
        out["origin_third"] = cls.get_pitch_third_series(out["x"])
        out["origin_corridor"] = cls.get_vertical_corridor_series(out["y"])
        out["origin_zone_18"] = cls.get_zone_18_series(out["x"], out["y"])
        out["origin_in_zone_14"] = cls.is_zone_14_series(out["x"], out["y"])
        out["origin_in_off_half_space"] = cls.is_offensive_half_space_series(
            out["x"], out["y"]
        )
        out["origin_in_box"] = cls.is_penalty_box_series(out["x"], out["y"])

        # 2. Classificação do destino (end_x, end_y)
        out["end_third"] = cls.get_pitch_third_series(out["end_x"])
        out["end_corridor"] = cls.get_vertical_corridor_series(out["end_y"])
        out["end_zone_18"] = cls.get_zone_18_series(out["end_x"], out["end_y"])
        out["end_in_zone_14"] = cls.is_zone_14_series(out["end_x"], out["end_y"])
        out["end_in_off_half_space"] = cls.is_offensive_half_space_series(
            out["end_x"], out["end_y"]
        )
        out["end_in_box"] = cls.is_penalty_box_series(out["end_x"], out["end_y"])

        # 3. Vetores de deslocamento (em jardas e metros)
        out["dx"] = (out["end_x"] - out["x"]).astype(float)
        out["dy"] = (out["end_y"] - out["y"]).astype(float)
        out["distance_yards"] = np.sqrt(out["dx"] ** 2 + out["dy"] ** 2)
        out["distance_meters"] = out["distance_yards"] * cls.YARD_TO_METER

        # 4. Ganho radial em direção ao gol (Goalward Progression)
        out["dist_to_goal_start"] = cls.distance_to_goal_yards(out["x"], out["y"])
        out["dist_to_goal_end"] = cls.distance_to_goal_yards(out["end_x"], out["end_y"])
        out["goal_progression_yards"] = (
            out["dist_to_goal_start"] - out["dist_to_goal_end"]
        )
        out["goal_progression_meters"] = (
            out["goal_progression_yards"] * cls.YARD_TO_METER
        )

        # 5. Critério Oficial de Ação Progressiva (Passes e Conduções completas)
        pass_outcome = out.get("pass_outcome_name", pd.Series(None, index=out.index))
        is_completed_pass = (out["type_name"] == "Pass") & (pass_outcome.isna())
        is_carry = out["type_name"] == "Carry"
        valid_action = is_completed_pass | is_carry

        cond_own_half = (
            (out["x"] < 60.0)
            & (out["end_x"] < 60.0)
            & (out["goal_progression_yards"] >= 30.0)
        )
        cond_cross_half = (
            (out["x"] < 60.0)
            & (out["end_x"] >= 60.0)
            & (out["goal_progression_yards"] >= 15.0)
        )
        cond_opp_half = (
            (out["x"] >= 60.0)
            & (out["end_x"] >= 60.0)
            & (out["goal_progression_yards"] >= 10.0)
        )

        out["is_progressive_action"] = (
            valid_action & (cond_own_half | cond_cross_half | cond_opp_half)
        ).fillna(False).astype(int)

        # 6. Entradas no Terço Final, na Zona 14, na Grande Área e Deep Completions
        out["is_final_third_entry"] = (
            valid_action & (out["x"] < 80.0) & (out["end_x"] >= 80.0)
        ).fillna(False).astype(int)

        out["is_box_entry"] = (
            valid_action & (out["origin_in_box"] == 0) & (out["end_in_box"] == 1)
        ).fillna(False).astype(int)

        out["is_zone_14_entry"] = (
            valid_action & (out["origin_in_zone_14"] == 0) & (out["end_in_zone_14"] == 1)
        ).fillna(False).astype(int)

        is_not_cross = out.get("is_pass_cross", pd.Series(0, index=out.index)).fillna(0) == 0
        out["is_deep_completion"] = (
            is_completed_pass
            & is_not_cross
            & (out["dist_to_goal_end"] <= 20.0)
        ).fillna(False).astype(int)

        return out

    @classmethod
    def compute_team_convex_hull(
        cls, coords_df: pd.DataFrame, trim_outliers_pct: float = 0.05
    ) -> Dict[str, float]:
        """
        Calcula o Polígono Convexo (Convex Hull) das posições usando Shapely.
        """
        clean = coords_df[["x", "y"]].dropna().astype(float)
        if len(clean) < 3:
            return {
                "hull_area_m2": 0.0,
                "width_m": 0.0,
                "length_m": 0.0,
                "centroid_x": float(clean["x"].mean()) if not clean.empty else 60.0,
                "centroid_y": float(clean["y"].mean()) if not clean.empty else 40.0,
            }

        centroid_x = float(clean["x"].mean())
        centroid_y = float(clean["y"].mean())

        if trim_outliers_pct > 0.0 and len(clean) >= 10:
            dists = np.sqrt((clean["x"] - centroid_x) ** 2 + (clean["y"] - centroid_y) ** 2)
            threshold = np.quantile(dists, 1.0 - trim_outliers_pct)
            filtered = clean[dists <= threshold]
            if len(filtered) >= 3:
                clean = filtered

        points = list(zip(clean["x"] * cls.YARD_TO_METER, clean["y"] * cls.YARD_TO_METER))
        multipoint = MultiPoint(points)
        hull = multipoint.convex_hull

        min_x, min_y, max_x, max_y = hull.bounds
        return {
            "hull_area_m2": round(float(hull.area), 2),
            "length_m": round(float(max_x - min_x), 2),
            "width_m": round(float(max_y - min_y), 2),
            "centroid_x": round(centroid_x, 2),
            "centroid_y": round(centroid_y, 2),
        }