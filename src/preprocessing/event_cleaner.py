"""
Módulo de Pré-processamento e Engenharia de Cadeias de Posse (Camada 2)
Enriquece os eventos brutos com geometria tática, identifica perdas/recuperações
de bola e agrega sequências completas de posse (Possession Chains).
"""

import numpy as np
import pandas as pd
from src.geometry.pitch_zones import PitchGeometry


class EventPreprocessor:
    """
    Limpa, padroniza e transforma eventos de partidas em features táticas
    e tabelas de sequências de posse prontas para os módulos de Métricas e ML.
    """

# Colunas opcionais que devem sempre existir no DataFrame enriquecido
    DEFAULT_OPTIONAL_COLS = {
        "position_name": "Unknown",
        "pass_outcome_name": None,
        "pass_type_name": None,
        "pass_height_name": None,
        "pass_recipient_name": None,
        "duel_outcome_name": None,
        "interception_outcome_name": None,
        "play_pattern_name": "Regular Play",
        "under_pressure": 0,
        "counterpress": 0,
        "ball_recovery_failure": 0,
        "is_pass_Switch": 0,
        "is_pass_cross": 0,
        "is_pass_through_ball": 0,
        "shot_statsbomb_xg": 0.0,
        "shot_outcome_name": None,
        "substitution_replacement_name": None,
        "tactics_formation": None,
    }

    @staticmethod
    def _parse_timestamp_to_seconds(
        timestamp_series: pd.Series, minute_series: pd.Series, second_series: pd.Series
    ) -> pd.Series:
        """
        Converte o timestamp do evento em segundos absolutos dentro da partida.
        """
        base_seconds = (
            pd.to_numeric(minute_series, errors="coerce").fillna(0.0) * 60.0
            + pd.to_numeric(second_series, errors="coerce").fillna(0.0)
        )
        return base_seconds.astype(float)

    @classmethod
    def process_match_events(cls, df_raw: pd.DataFrame) -> pd.DataFrame:
        """
        Pipeline completo de enriquecimento por evento:
        0. Garante colunas opcionais padrão (para suportar CSVs parciais e mocks de teste).
        1. Calcula tempo contínuo em segundos.
        2. Aplica geometria espacial de 18 zonas, 5 corredores e Zona 14.
        3. Identifica passes completos, turnovers (perdas de posse) e ações defensivas.
        """
        if df_raw.empty:
            return df_raw.copy()

        df = df_raw.copy()

        # 0. Garante que todas as colunas opcionais existam
        for col_name, default_val in cls.DEFAULT_OPTIONAL_COLS.items():
            if col_name not in df.columns:
                df[col_name] = default_val

        df["shot_statsbomb_xg"] = (
            pd.to_numeric(df["shot_statsbomb_xg"], errors="coerce")
            .fillna(0.0)
            .astype(float)
        )
        for int_col in [
            "under_pressure",
            "counterpress",
            "ball_recovery_failure",
            "is_pass_Switch",
            "is_pass_cross",
            "is_pass_through_ball",
        ]:
            df[int_col] = (
                pd.to_numeric(df[int_col], errors="coerce").fillna(0).astype(int)
            )
        # Converte nomes cartoriais completos para o Nome Comum do futebol
        from src.ingestion.brazil_and_multi_source import PlayerNameNormalizer

        if "player_name" in df.columns:
            df["player_name"] = df["player_name"].apply(
                lambda x: PlayerNameNormalizer.to_common_name(x) if pd.notna(x) else x
            )
        if "pass_recipient_name" in df.columns:
            df["pass_recipient_name"] = df["pass_recipient_name"].apply(
                lambda x: PlayerNameNormalizer.to_common_name(x) if pd.notna(x) else x
            )
        df = df.sort_values(["match_id", "period", "index_num"]).reset_index(drop=True)

        # 1. Tempo contínuo em segundos
        df["time_seconds"] = cls._parse_timestamp_to_seconds(
            df.get("timestamp", pd.Series(dtype=str)),
            df["minute"],
            df["second"],
        )

        # 2. Enriquecimento Geométrico (Camada PitchGeometry)
        df = PitchGeometry.enrich_spatial_features(df)

        # 3. Classificação Booleana de Sucesso do Passe
        df["is_pass"] = (df["type_name"] == "Pass").astype(int)
        df["is_pass_completed"] = (
            (df["type_name"] == "Pass") & (df["pass_outcome_name"].isna())
        ).astype(int)

        # 4. Identificação de Perda de Posse (Turnover Técnico ou Passe Incompleto)
        is_incomplete_pass = (df["type_name"] == "Pass") & (
            df["pass_outcome_name"].notna()
            & ~df["pass_outcome_name"].isin(["Injury Clearance", "Out"])
        )
        is_miscontrol = df["type_name"] == "Miscontrol"
        is_dispossessed = df["type_name"] == "Dispossessed"
        is_failed_dribble = (df["type_name"] == "Dribble") & (
            df["duel_outcome_name"] == "Lost"
        )

        df["is_turnover"] = (
            is_incomplete_pass | is_miscontrol | is_dispossessed | is_failed_dribble
        ).fillna(False).astype(int)

        # 5. Identificação de Ações Defensivas de Engajamento
        defensive_types = {
            "Duel",
            "Interception",
            "Ball Recovery",
            "Block",
            "Clearance",
            "Foul Committed",
            "Pressure",
        }
        df["is_defensive_action"] = df["type_name"].isin(defensive_types).astype(int)

        # 6. Recuperação Limpa de Posse
        df["is_ball_recovery"] = (
            ((df["type_name"] == "Ball Recovery") & (df["ball_recovery_failure"] == 0))
            | (
                (df["type_name"] == "Interception")
                & (
                    df["interception_outcome_name"].isin(
                        ["Won", "Success", "Success In Play", "Success Out"]
                    )
                )
            )
        ).fillna(False).astype(int)

        return df

    @classmethod
    def build_possession_chains(cls, df_enriched: pd.DataFrame) -> pd.DataFrame:
        """
        Agrega os eventos individuais em Cadeias de Posse (Possession Chains).
        """
        if df_enriched.empty or "possession" not in df_enriched.columns:
            return pd.DataFrame()

        in_poss = df_enriched[
            df_enriched["team_name"] == df_enriched["possession_team_name"]
        ].copy()
        in_poss = in_poss[in_poss["x"].notna()].copy()

        if in_poss.empty:
            return pd.DataFrame()

        chains = []
        grouped = in_poss.groupby(["match_id", "period", "possession"], sort=False)

        for (match_id, period, poss_id), grp in grouped:
            team_name = str(grp["team_name"].iloc[0])
            start_row = grp.iloc[0]
            end_row = grp.iloc[-1]

            x_start = float(start_row["x"])
            y_start = float(start_row["y"])

            last_x_val = end_row["end_x"] if pd.notna(end_row["end_x"]) else end_row["x"]
            last_y_val = end_row["end_y"] if pd.notna(end_row["end_y"]) else end_row["y"]
            x_end = float(last_x_val)
            y_end = float(last_y_val)

            t_start = float(grp["time_seconds"].min())
            t_end = float(grp["time_seconds"].max())
            duration = max(t_end - t_start, 1.0)

            net_dx_yards = x_end - x_start
            net_progression_m = net_dx_yards * PitchGeometry.YARD_TO_METER
            direct_speed_m_s = net_progression_m / duration

            num_passes = int(grp["is_pass"].sum())
            completed_passes = int(grp["is_pass_completed"].sum())
            progressive_actions = int(grp["is_progressive_action"].sum())
            entered_zone_14 = int(
                (grp["origin_in_zone_14"].max() == 1)
                or (grp["end_in_zone_14"].max() == 1)
            )
            entered_box = int(
                (grp["origin_in_box"].max() == 1) or (grp["end_in_box"].max() == 1)
            )

            shots_in_chain = grp[grp["type_name"] == "Shot"]
            ended_in_shot = 1 if len(shots_in_chain) > 0 else 0
            chain_xg = (
                float(shots_in_chain["shot_statsbomb_xg"].fillna(0.0).sum())
                if "shot_statsbomb_xg" in shots_in_chain.columns
                else 0.0
            )

            is_counter_attack = int(
                (x_start < 75.0)
                & (net_progression_m >= 20.0)
                & (direct_speed_m_s >= 2.2)
            )

            chains.append(
                {
                    "match_id": int(match_id),
                    "period": int(period),
                    "possession_id": int(poss_id),
                    "team_name": team_name,
                    "start_third": str(start_row["origin_third"]),
                    "start_corridor": str(start_row["origin_corridor"]),
                    "x_start": round(x_start, 2),
                    "y_start": round(y_start, 2),
                    "x_end": round(x_end, 2),
                    "y_end": round(y_end, 2),
                    "duration_sec": round(duration, 2),
                    "num_events": int(len(grp)),
                    "num_passes": num_passes,
                    "completed_passes": completed_passes,
                    "progressive_actions": progressive_actions,
                    "net_progression_m": round(net_progression_m, 2),
                    "direct_speed_m_s": round(direct_speed_m_s, 2),
                    "entered_zone_14": entered_zone_14,
                    "entered_box": entered_box,
                    "is_counter_attack": is_counter_attack,
                    "ended_in_shot": ended_in_shot,
                    "chain_xg": round(chain_xg, 4),
                    "under_pressure_ratio": round(float(grp["under_pressure"].mean()), 3),
                }
            )

        return pd.DataFrame(chains)