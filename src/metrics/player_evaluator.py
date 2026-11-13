"""
Módulo de Análise Individual de Atletas e Prescrição de Substituições (Camadas 3.G e 3.H)
Avalia desempenho técnico-tático individual, compara jogadores da mesma função e
diagnostica necessidades de substituição com base em queda de eficiência temporal
e exposição estrutural, declarando explicitamente as limitações de dados físicos/GPS.
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from src.metrics.xt_model import ExpectedThreatModel


class PlayerTacticalEvaluator:
    """
    Motor de avaliação individual e análise de substituições.
    Regra obrigatória: nunca recomendar substituição apenas por volume baixo sem
    contextualizar a função tática, a evolução temporal no jogo e os riscos estruturais.
    """

    @staticmethod
    def _ensure_xt_columns(df_events: pd.DataFrame) -> pd.DataFrame:
        if "delta_xt" not in df_events.columns or "is_line_breaking_pass" not in df_events.columns:
            return ExpectedThreatModel.enrich_events_with_xt(df_events)
        return df_events

    @classmethod
    def evaluate_team_players(
        cls, df_events: pd.DataFrame, target_team: str
    ) -> pd.DataFrame:
        """
        Gera a tabela analítica completa de todos os jogadores que atuaram pela equipe
        na partida, incluindo métricas de construção, progressão, xT, retenção e defesa.
        """
        df = cls._ensure_xt_columns(df_events)
        team_ev = df[
            (df["team_name"] == target_team) & (df["player_name"].notna())
        ].copy()

        if team_ev.empty:
            return pd.DataFrame()

        total_team_passes = max(int((team_ev["type_name"] == "Pass").sum()), 1)
        player_rows: List[Dict[str, Any]] = []

        for player_name, grp in team_ev.groupby("player_name", sort=False):
            pos_mode = grp["position_name"].dropna().mode()
            position = str(pos_mode.iloc[0]) if not pos_mode.empty else "Unknown"

            min_start = int(grp["minute"].min())
            min_end = int(grp["minute"].max())
            est_minutes = max(min_end - min_start, 5)

            passes = grp[grp["type_name"] == "Pass"]
            n_passes = int(len(passes))
            comp_passes = int(passes["is_pass_completed"].sum())
            pass_acc_pct = (
                round((comp_passes / n_passes) * 100.0, 2) if n_passes > 0 else 0.0
            )

            press_passes = passes[passes["under_pressure"] == 1]
            n_press_passes = int(len(press_passes))
            press_retention_pct = (
                round(
                    (press_passes["is_pass_completed"].sum() / n_press_passes) * 100.0,
                    2,
                )
                if n_press_passes > 0
                else 100.0
            )

            prog_actions = int(grp["is_progressive_action"].sum())
            line_breaking = int(grp["is_line_breaking_pass"].sum())
            z14_entries = int(grp["is_zone_14_entry"].sum())
            box_entries = int(grp["is_box_entry"].sum())
            turnovers = int(grp["is_turnover"].sum())
            def_actions = int(grp["is_defensive_action"].sum())
            recoveries = int(grp["is_ball_recovery"].sum())
            counterpress_actions = int(grp["counterpress"].sum())

            shots = grp[grp["type_name"] == "Shot"]
            n_shots = int(len(shots))
            xg_total = round(float(shots["shot_statsbomb_xg"].fillna(0.0).sum()), 3)
            xt_generated = round(
                float(grp[grp["delta_xt"] > 0]["delta_xt"].sum()), 4
            )

            # Análise de Fadiga Funcional / Queda de Eficiência (0-60 min vs >60 min)
            early_passes = passes[passes["minute"] < 60]
            late_passes = passes[passes["minute"] >= 60]
            early_acc = (
                round(
                    (early_passes["is_pass_completed"].sum() / len(early_passes))
                    * 100.0,
                    2,
                )
                if len(early_passes) >= 3
                else np.nan
            )
            late_acc = (
                round(
                    (late_passes["is_pass_completed"].sum() / len(late_passes)) * 100.0,
                    2,
                )
                if len(late_passes) >= 3
                else np.nan
            )
            late_turnovers = int(grp[grp["minute"] >= 60]["is_turnover"].sum())

            if pd.notna(early_acc) and pd.notna(late_acc):
                acc_drop_after_60_pct = round(float(early_acc - late_acc), 2)
            else:
                acc_drop_after_60_pct = 0.0

            player_rows.append(
                {
                    "player_name": str(player_name),
                    "position_name": position,
                    "first_action_min": min_start,
                    "last_action_min": min_end,
                    "estimated_minutes_active": est_minutes,
                    "total_actions": int(len(grp)),
                    "passes_attempted": n_passes,
                    "passes_completed": comp_passes,
                    "pass_accuracy_pct": pass_acc_pct,
                    "team_pass_share_pct": round(
                        (n_passes / total_team_passes) * 100.0, 2
                    ),
                    "pressured_passes": n_press_passes,
                    "press_retention_pct": press_retention_pct,
                    "progressive_actions": prog_actions,
                    "line_breaking_passes": line_breaking,
                    "zone_14_entries": z14_entries,
                    "box_entries": box_entries,
                    "xt_generated": xt_generated,
                    "shots": n_shots,
                    "xg": xg_total,
                    "turnovers": turnovers,
                    "defensive_actions": def_actions,
                    "ball_recoveries": recoveries,
                    "counterpress_actions": counterpress_actions,
                    "pass_acc_0_60_pct": early_acc if pd.notna(early_acc) else pass_acc_pct,
                    "pass_acc_60_plus_pct": late_acc if pd.notna(late_acc) else pass_acc_pct,
                    "accuracy_drop_after_60_pct": acc_drop_after_60_pct,
                    "turnovers_after_60": late_turnovers,
                }
            )

        out_df = pd.DataFrame(player_rows)
        if out_df.empty:
            return out_df

        # Calcula Índice Tático Composto (0 a 100) ponderando criação, progressão, segurança e defesa
        out_df["tactical_impact_score"] = (
            (out_df["progressive_actions"] * 2.5)
            + (out_df["line_breaking_passes"] * 3.0)
            + (out_df["xt_generated"] * 45.0)
            + (out_df["ball_recoveries"] * 2.0)
            + (out_df["box_entries"] * 3.5)
            + (out_df["xg"] * 18.0)
            - (out_df["turnovers"] * 1.8)
        ).round(2)

        return out_df.sort_values(
            by=["tactical_impact_score", "passes_completed"], ascending=False
        ).reset_index(drop=True)

    @classmethod
    def compare_players_head_to_head(
        cls,
        df_players: pd.DataFrame,
        player_a: str,
        player_b: str,
    ) -> Dict[str, Any]:
        """
        Compara diretamente dois jogadores (ex: os dois volantes ou dois pontas),
        destacando as vantagens táticas relativas e a complementaridade de funções.
        """
        row_a = df_players[df_players["player_name"] == player_a]
        row_b = df_players[df_players["player_name"] == player_b]

        if row_a.empty or row_b.empty:
            return {"status": "PLAYER_NOT_FOUND"}

        a = row_a.iloc[0].to_dict()
        b = row_b.iloc[0].to_dict()

        metrics_to_compare = [
            "passes_completed",
            "pass_accuracy_pct",
            "press_retention_pct",
            "progressive_actions",
            "line_breaking_passes",
            "xt_generated",
            "ball_recoveries",
            "turnovers",
            "tactical_impact_score",
        ]

        deltas = {}
        for m in metrics_to_compare:
            deltas[m] = {
                player_a: a[m],
                player_b: b[m],
                "diff_a_minus_b": round(float(a[m]) - float(b[m]), 4),
            }

        # Define perfil funcional predominante de cada um com base nos dados
        def _infer_role_style(p: Dict[str, Any]) -> str:
            if p["line_breaking_passes"] >= 4 and p["progressive_actions"] >= 6:
                return "Construtor Progressivo / Quebrador de Linhas"
            if p["ball_recoveries"] >= 6 and p["defensive_actions"] >= 10:
                return "Recuperador / Âncora de Equilíbrio Defensivo"
            if p["box_entries"] >= 2 or p["xg"] >= 0.25:
                return "Infiltrador de Terço Final / Atacante de Espaço"
            return "Circulador de Posse / Apoio Estrutural"

        return {
            "status": "OK",
            "player_a": player_a,
            "player_a_position": a["position_name"],
            "player_a_inferred_role": _infer_role_style(a),
            "player_b": player_b,
            "player_b_position": b["position_name"],
            "player_b_inferred_role": _infer_role_style(b),
            "comparison_metrics": deltas,
        }

    @classmethod
    def recommend_tactical_substitutions(
        cls, df_events: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        H. Avalia substituições necessárias ou realizadas considerando:
        - Queda acentuada de precisão de passe e retenção após o minuto 60
        - Acúmulo de perdas de posse (turnovers) em zonas críticas
        - Risco estrutural de remover um jogador com alta centralidade ou recuperação defensiva
        - Aviso explícito de limitação de dados fisiológicos/GPS
        """
        df_players = cls.evaluate_team_players(df_events, target_team)
        if df_players.empty:
            return {"team_name": target_team, "recommendations": []}

        # Filtra atletas que iniciaram a partida (primeira ação antes dos 15 min) e atuaram >= 40 min
        starters = df_players[
            (df_players["first_action_min"] <= 15)
            & (df_players["estimated_minutes_active"] >= 40)
        ].copy()

        recommendations: List[Dict[str, Any]] = []

        for _, p in starters.iterrows():
            reasons = []
            risk_factors = []
            priority_score = 0.0

            # Critério 1: Degradação técnica severa após o minuto 60
            if p["accuracy_drop_after_60_pct"] >= 12.0 and p["turnovers_after_60"] >= 2:
                reasons.append(
                    f"Queda de {p['accuracy_drop_after_60_pct']} pp na precisão de passe após o minuto 60 "
                    f"(de {p['pass_acc_0_60_pct']}% para {p['pass_acc_60_plus_pct']}%), acompanhada de "
                    f"{p['turnovers_after_60']} perdas de posse no terço final do jogo."
                )
                priority_score += 45.0

            # Critério 2: Baixa resistência à pressão combinada com alto volume de perdas
            if p["pressured_passes"] >= 5 and p["press_retention_pct"] < 62.0 and p["turnovers"] >= 4:
                reasons.append(
                    f"Vulnerabilidade sob pressão adversária: apenas {p['press_retention_pct']}% de retenção "
                    f"em passes pressionados ({p['pressured_passes']} tentativas) e {p['turnovers']} turnovers totais."
                )
                priority_score += 35.0

            # Critério 3: Baixa geração progressiva em função de meio/ataque
            if (
                any(k in p["position_name"] for k in ["Wing", "Midfield", "Forward"])
                and p["progressive_actions"] <= 1
                and p["xt_generated"] < 0.025
                and p["turnovers"] >= 3
            ):
                reasons.append(
                    f"Baixa capacidade de ruptura territorial na função ({p['position_name']}): apenas "
                    f"{p['progressive_actions']} ação progressiva, +{p['xt_generated']:.4f} xT gerado e {p['turnovers']} perdas."
                )
                priority_score += 25.0

            if not reasons:
                continue

            # Avalia o risco estrutural de tirar esse jogador de campo
            if p["team_pass_share_pct"] >= 12.0:
                risk_factors.append(
                    f"ALTO RISCO ESTRUTURAL NA SAÍDA DE BOLA: O atleta concentra {p['team_pass_share_pct']}% "
                    f"dos passes da equipe ({p['passes_attempted']} passes). O substituto precisa ter perfil "
                    f"de apoio curto e resistência à pressão para evitar colapso na circulação."
                )
            if p["ball_recoveries"] >= 6 or p["defensive_actions"] >= 10:
                risk_factors.append(
                    f"RISCO DE DESPROTEÇÃO DEFENSIVA: O atleta soma {p['ball_recoveries']} recuperações de bola "
                    f"e {p['defensive_actions']} ações defensivas. Sua saída exige recomposição imediata do setor."
                )
            if not risk_factors:
                risk_factors.append(
                    "Risco estrutural moderado/baixo: a alteração não desfaz o eixo principal de saída de bola."
                )

            # Perfil recomendado para o substituto entrar
            if "Wing" in p["position_name"] or "Forward" in p["position_name"]:
                ideal_replacement_profile = (
                    "Atacante/Extremo de velocidade e ataque ao espaço (ruptura em profundidade) "
                    "para explorar a linha defensiva adversária desgastada e recompor o corredor."
                )
            elif "Midfield" in p["position_name"]:
                ideal_replacement_profile = (
                    "Meio-campista/Volante com alta taxa de retenção sob pressão (Press Resistance > 80%) "
                    "e capacidade de passe progressivo para estabilizar o controle central."
                )
            else:
                ideal_replacement_profile = (
                    "Defensor/Lateral com vigor para duelos 1v1 no corredor e segurança no passe de saída."
                )

            recommendations.append(
                {
                    "candidate_out": p["player_name"],
                    "position": p["position_name"],
                    "priority_score": round(priority_score, 1),
                    "tactical_reasons": reasons,
                    "ideal_replacement_profile": ideal_replacement_profile,
                    "structural_risks_of_substitution": risk_factors,
                }
            )

        recommendations = sorted(
            recommendations, key=lambda r: r["priority_score"], reverse=True
        )

        # Também lista as substituições reais que ocorreram na partida para auditoria
        subs_df = df_events[
            (df_events["team_name"] == target_team)
            & (df_events["type_name"] == "Substitution")
        ].copy()
        for col in ["minute", "player_name", "substitution_replacement_name", "position_name"]:
            if col not in subs_df.columns:
                subs_df[col] = None
        real_subs = subs_df[
            ["minute", "player_name", "substitution_replacement_name", "position_name"]
        ].to_dict(orient="records")

        return {
            "team_name": target_team,
            "recommended_substitutions": recommendations[:3],
            "actual_match_substitutions": real_subs,
            "data_limitations_notice": (
                "LIMITAÇÃO EXPLÍCITA DE DADOS: Os dados de eventos não contêm telemetria fisiológica "
                "(GPS, distância em alta intensidade >25 km/h, frequência cardíaca ou estado clínico do banco). "
                "As recomendações baseiam-se exclusivamente na degradação técnica observada nos eventos (0-60 min vs >60 min) "
                "e no balanço estrutural da equipe."
            ),
        }