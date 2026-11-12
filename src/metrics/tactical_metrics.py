"""
Módulo de Métricas Táticas Coletivas por Fase do Jogo (Camada 2 - Métricas)
Calcula indicadores determinísticos e rastreáveis para:
A. Organização Defensiva (PPDA, Altura do Bloco, Vulnerabilidade por Corredor, Inversões)
B. Organização Ofensiva (Saída de Bola, Ocupação da Zona 14, Progressão por Corredor)
C. Transição Ofensiva (Velocidade Direta, Contra-Ataques, Conversão)
D. Transição Defensiva (Gegenpressing em 5s pós-perda, Exposição a Contra-Ataques)
E. Meio-Campo (Field Tilt, Dominância Central, Retenção sob Pressão)
F. Bolas Paradas (Escanteios e Faltas Ofensivas/Defensivas por Zona Alvo)
"""

from typing import Any, Dict, List
import numpy as np
import pandas as pd
from src.geometry.pitch_zones import PitchGeometry


class TacticalMetricsEngine:
    """
    Motor matemático que extrai indicadores táticos por fase do jogo a partir
    dos eventos enriquecidos e das cadeias de posse (Possession Chains).
    Regra estrita: todo percentual é acompanhado de seu numerador e denominador (sample_size).
    """

    YARD_TO_M = PitchGeometry.YARD_TO_METER

    @staticmethod
    def _invert_corridor_perspective(opponent_corridor: str) -> str:
        """
        Inverte a lateralidade do corredor do atacante adversário para a perspectiva
        do sistema defensivo analisado:
        Se o adversário ataca pela Esquerda dele -> ataca o nosso Corredor Defensivo Direito.
        """
        mapping = {
            "Corredor Lateral Esquerdo": "Setor Defensivo Direito (Lateral-Direito)",
            "Meio-Espaço Esquerdo": "Meio-Espaço Defensivo Direito (Entre LD e Zagueiro Dir.)",
            "Corredor Central": "Eixo Central Defensivo (Zagueiros / Volante Central)",
            "Meio-Espaço Direito": "Meio-Espaço Defensivo Esquerdo (Entre LE e Zagueiro Esq.)",
            "Corredor Lateral Direito": "Setor Defensivo Esquerdo (Lateral-Esquerdo)",
        }
        return mapping.get(opponent_corridor, "Indefinido")

    @classmethod
    def compute_defensive_organization(
        cls, df_events: pd.DataFrame, df_chains: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        A. Calcula métricas de Organização Defensiva da equipe `target_team`:
        - PPDA (Passes Allowed Per Defensive Action)
        - Altura média da linha de engajamento defensivo (em metros) e dispersão
        - Vulnerabilidade detalhada pelos 5 corredores defensivos (progressões cedidas, entradas na área, xG)
        - Comportamento diante de inversões de jogo (Switches of Play) do adversário
        """
        team_ev = df_events[df_events["team_name"] == target_team]
        opp_ev = df_events[df_events["team_name"] != target_team]
        opp_chains = df_chains[df_chains["team_name"] != target_team]

        # 1. Cálculo do PPDA
        # Passes do adversário nos primeiros 60% do campo dele (x <= 72 jardas)
        opp_passes_build_zone = opp_ev[
            (opp_ev["type_name"] == "Pass") & (opp_ev["x"] <= 72.0)
        ]
        # Ações defensivas ativas da nossa equipe nos 60% finais do campo (x >= 48 jardas)
        active_def_types = {"Duel", "Interception", "Foul Committed", "Block", "Pressure"}
        team_high_def_actions = team_ev[
            (team_ev["type_name"].isin(active_def_types)) & (team_ev["x"] >= 48.0)
        ]

        n_opp_passes = int(len(opp_passes_build_zone))
        n_def_actions = int(len(team_high_def_actions))
        ppda = round(n_opp_passes / max(n_def_actions, 1), 2)

        # 2. Altura e Compactação Longitudinal das Ações Defensivas
        def_actions_all = team_ev[
            (team_ev["is_defensive_action"] == 1) & (team_ev["x"].notna())
        ]
        if not def_actions_all.empty:
            avg_def_height_m = round(
                float(def_actions_all["x"].mean()) * cls.YARD_TO_M, 2
            )
            std_def_length_m = round(
                float(def_actions_all["x"].std(ddof=0)) * cls.YARD_TO_M, 2
            )
            std_def_width_m = round(
                float(def_actions_all["y"].std(ddof=0)) * cls.YARD_TO_M, 2
            )
        else:
            avg_def_height_m, std_def_length_m, std_def_width_m = 40.0, 0.0, 0.0

        if avg_def_height_m >= 44.0:
            block_profile = "Bloco Alto / Pressão Avançada"
        elif avg_def_height_m >= 36.5:
            block_profile = "Bloco Médio Equilibrado"
        else:
            block_profile = "Bloco Baixo / Contenção Posicional"

        # 3. Vulnerabilidade pelos 5 Corredores Defensivos
        opp_prog = opp_ev[opp_ev["is_progressive_action"] == 1].copy()
        opp_prog["defensive_sector"] = opp_prog["end_corridor"].apply(
            cls._invert_corridor_perspective
        )
        total_opp_prog = max(len(opp_prog), 1)

        corridor_vulnerability: Dict[str, Dict[str, Any]] = {}
        all_def_sectors = [
            "Setor Defensivo Direito (Lateral-Direito)",
            "Meio-Espaço Defensivo Direito (Entre LD e Zagueiro Dir.)",
            "Eixo Central Defensivo (Zagueiros / Volante Central)",
            "Meio-Espaço Defensivo Esquerdo (Entre LE e Zagueiro Esq.)",
            "Setor Defensivo Esquerdo (Lateral-Esquerdo)",
        ]

        for sector in all_def_sectors:
            sec_prog = opp_prog[opp_prog["defensive_sector"] == sector]
            n_prog = int(len(sec_prog))
            box_entries_conceded = int(sec_prog["is_box_entry"].sum())
            corridor_vulnerability[sector] = {
                "progressive_actions_conceded": n_prog,
                "share_of_opponent_progression_pct": round(
                    (n_prog / total_opp_prog) * 100.0, 2
                ),
                "box_entries_conceded": box_entries_conceded,
            }

        most_vulnerable_sector = max(
            corridor_vulnerability.items(),
            key=lambda kv: kv[1]["progressive_actions_conceded"],
        )[0]

        # 4. Comportamento diante de Inversões de Jogo (Switches of Play)
        opp_switches = opp_ev[
            (opp_ev["type_name"] == "Pass")
            & (
                (opp_ev["is_pass_Switch"] == 1)
                | (opp_ev["dy"].abs() >= 35.0)
            )
        ]
        completed_switches = opp_switches[opp_switches["is_pass_completed"] == 1]
        n_switches = int(len(opp_switches))
        n_comp_switches = int(len(completed_switches))
        switch_success_conceded_pct = (
            round((n_comp_switches / n_switches) * 100.0, 2) if n_switches > 0 else 0.0
        )

        # 5. Concessão de Entradas na Zona 14 e Deep Completions
        z14_conceded = int(opp_ev["is_zone_14_entry"].sum())
        deep_comp_conceded = int(opp_ev["is_deep_completion"].sum())
        shots_conceded = opp_ev[opp_ev["type_name"] == "Shot"]
        xg_conceded = round(float(shots_conceded["shot_statsbomb_xg"].fillna(0).sum()), 3)

        return {
            "ppda": ppda,
            "ppda_numerator_opp_passes": n_opp_passes,
            "ppda_denominator_def_actions": n_def_actions,
            "avg_defensive_engagement_height_m": avg_def_height_m,
            "longitudinal_dispersion_m": std_def_length_m,
            "lateral_dispersion_m": std_def_width_m,
            "block_profile": block_profile,
            "zone_14_entries_conceded": z14_conceded,
            "deep_completions_conceded": deep_comp_conceded,
            "shots_conceded": int(len(shots_conceded)),
            "xg_conceded": xg_conceded,
            "switches_faced": n_switches,
            "switches_completed_by_opponent": n_comp_switches,
            "switch_conceded_rate_pct": switch_success_conceded_pct,
            "most_vulnerable_defensive_sector": most_vulnerable_sector,
            "corridor_vulnerability_breakdown": corridor_vulnerability,
            "total_opponent_progressive_actions": int(len(opp_prog)),
        }

    @classmethod
    def compute_offensive_organization(
        cls, df_events: pd.DataFrame, df_chains: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        B. Calcula métricas de Organização Ofensiva:
        - Perfil de saída de bola (curta vs. longa no terço defensivo) e taxa de retenção
        - Progressão pelos 5 corredores ofensivos
        - Ocupação e entradas na Zona 14 e Meios-Espaços Ofensivos
        - Entradas na Grande Área, Deep Completions e xG em bola rolando
        """
        team_ev = df_events[df_events["team_name"] == target_team]
        team_passes = team_ev[team_ev["type_name"] == "Pass"]

        # 1. Saída de Bola no Terço Defensivo (x < 40)
        buildup_passes = team_passes[team_passes["x"] < 40.0]
        n_buildup = int(len(buildup_passes))
        long_buildup = buildup_passes[buildup_passes["distance_yards"] >= 32.0]
        short_buildup = buildup_passes[buildup_passes["distance_yards"] < 32.0]

        short_buildup_ratio_pct = (
            round((len(short_buildup) / n_buildup) * 100.0, 2) if n_buildup > 0 else 0.0
        )
        buildup_completion_pct = (
            round((buildup_passes["is_pass_completed"].sum() / n_buildup) * 100.0, 2)
            if n_buildup > 0
            else 0.0
        )
        buildup_turnovers = int(
            team_ev[(team_ev["x"] < 40.0) & (team_ev["is_turnover"] == 1)].shape[0]
        )

        # 2. Progressão pelos 5 Corredores Ofensivos
        prog_ev = team_ev[team_ev["is_progressive_action"] == 1]
        total_prog = max(len(prog_ev), 1)
        corridor_progression: Dict[str, Dict[str, Any]] = {}

        for corr in [
            "Corredor Lateral Esquerdo",
            "Meio-Espaço Esquerdo",
            "Corredor Central",
            "Meio-Espaço Direito",
            "Corredor Lateral Direito",
        ]:
            c_df = prog_ev[prog_ev["end_corridor"] == corr]
            count_c = int(len(c_df))
            corridor_progression[corr] = {
                "progressive_actions": count_c,
                "share_pct": round((count_c / total_prog) * 100.0, 2),
                "box_entries_from_corridor": int(c_df["is_box_entry"].sum()),
            }

        preferred_attack_corridor = max(
            corridor_progression.items(),
            key=lambda kv: kv[1]["progressive_actions"],
        )[0]

        # 3. Criação no Terço Final (Zona 14, Half-Spaces, Grande Área)
        z14_entries = int(team_ev["is_zone_14_entry"].sum())
        half_space_touches = int(team_ev["origin_in_off_half_space"].sum())
        box_entries = int(team_ev["is_box_entry"].sum())
        deep_completions = int(team_ev["is_deep_completion"].sum())
        through_balls = int(team_passes["is_pass_through_ball"].sum())
        crosses = int(team_passes["is_pass_cross"].sum())

        team_shots = team_ev[team_ev["type_name"] == "Shot"]
        total_xg = round(float(team_shots["shot_statsbomb_xg"].fillna(0).sum()), 3)

        return {
            "total_passes": int(len(team_passes)),
            "overall_pass_completion_pct": round(
                (team_passes["is_pass_completed"].sum() / max(len(team_passes), 1))
                * 100.0,
                2,
            ),
            "buildup_passes_count": n_buildup,
            "short_buildup_ratio_pct": short_buildup_ratio_pct,
            "buildup_completion_pct": buildup_completion_pct,
            "buildup_turnovers_in_own_third": buildup_turnovers,
            "total_progressive_actions": int(len(prog_ev)),
            "preferred_attack_corridor": preferred_attack_corridor,
            "corridor_progression_breakdown": corridor_progression,
            "zone_14_entries": z14_entries,
            "offensive_half_space_actions": half_space_touches,
            "penalty_box_entries": box_entries,
            "deep_completions": deep_completions,
            "through_balls_attempted": through_balls,
            "crosses_attempted": crosses,
            "total_shots": int(len(team_shots)),
            "total_xg": total_xg,
        }

    @classmethod
    def compute_offensive_transition(
        cls, df_events: pd.DataFrame, df_chains: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        C. Calcula métricas de Transição Ofensiva:
        - Velocidade vertical média de progressão após recuperar a bola (m/s)
        - Quantidade e taxa de sucesso de contra-ataques (terminados em chute ou área)
        - Jogadores mais acionados para puxar a transição rápida
        """
        team_chains = df_chains[df_chains["team_name"] == target_team]
        counters = team_chains[team_chains["is_counter_attack"] == 1]

        n_chains = int(len(team_chains))
        n_counters = int(len(counters))
        avg_speed = (
            round(float(team_chains["direct_speed_m_s"].mean()), 2)
            if n_chains > 0
            else 0.0
        )
        counter_speed = (
            round(float(counters["direct_speed_m_s"].mean()), 2)
            if n_counters > 0
            else 0.0
        )

        counters_to_box_or_shot = counters[
            (counters["entered_box"] == 1) | (counters["ended_in_shot"] == 1)
        ]
        counter_efficiency_pct = (
            round((len(counters_to_box_or_shot) / n_counters) * 100.0, 2)
            if n_counters > 0
            else 0.0
        )

        # Identifica os atletas mais acionados em posses de contra-ataque
        counter_poss_ids = set(counters["possession_id"].tolist())
        team_ev = df_events[
            (df_events["team_name"] == target_team)
            & (df_events["possession"].isin(counter_poss_ids))
            & (df_events["type_name"].isin(["Pass", "Carry"]))
        ]
        top_transition_players = (
            team_ev["player_name"]
            .dropna()
            .value_counts()
            .head(3)
            .to_dict()
        )

        return {
            "total_possessions_analyzed": n_chains,
            "overall_direct_speed_m_s": avg_speed,
            "counter_attacks_count": n_counters,
            "counter_attack_avg_speed_m_s": counter_speed,
            "counter_attacks_reaching_box_or_shot": int(len(counters_to_box_or_shot)),
            "counter_efficiency_pct": counter_efficiency_pct,
            "top_transition_hub_players": top_transition_players,
        }

    @classmethod
    def compute_defensive_transition(
        cls, df_events: pd.DataFrame, df_chains: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        D. Calcula métricas de Transição Defensiva (Pós-Perda):
        - Volume de ações de Counterpress (Gegenpressing)
        - Taxa de reação imediata nos 5 segundos após perder a bola no campo ofensivo (x >= 60)
        - Contra-ataques cedidos ao adversário e corredor mais exposto na transição
        """
        team_ev = df_events[df_events["team_name"] == target_team]
        opp_chains = df_chains[df_chains["team_name"] != target_team]

        high_turnovers = team_ev[
            (team_ev["is_turnover"] == 1) & (team_ev["x"] >= 60.0)
        ]
        n_high_turnovers = int(len(high_turnovers))

        # Avalia janela de 5 segundos após cada perda no campo de ataque
        immediate_press_count = 0
        immediate_recovery_count = 0

        for _, row in high_turnovers.iterrows():
            t0 = float(row["time_seconds"])
            p0 = int(row["period"])
            window = df_events[
                (df_events["period"] == p0)
                & (df_events["time_seconds"] > t0)
                & (df_events["time_seconds"] <= t0 + 5.0)
            ]
            team_window = window[window["team_name"] == target_team]
            if (
                (team_window["counterpress"] == 1).any()
                or (team_window["is_defensive_action"] == 1).any()
            ):
                immediate_press_count += 1
            if (team_window["is_ball_recovery"] == 1).any():
                immediate_recovery_count += 1

        gegenpress_reaction_pct = (
            round((immediate_press_count / n_high_turnovers) * 100.0, 2)
            if n_high_turnovers > 0
            else 0.0
        )
        post_loss_recovery_5s_pct = (
            round((immediate_recovery_count / n_high_turnovers) * 100.0, 2)
            if n_high_turnovers > 0
            else 0.0
        )

        opp_counters = opp_chains[opp_chains["is_counter_attack"] == 1]

        return {
            "turnovers_in_attacking_half": n_high_turnovers,
            "counterpress_events_total": int(team_ev["counterpress"].sum()),
            "post_loss_5s_press_reaction_count": immediate_press_count,
            "post_loss_5s_press_reaction_pct": gegenpress_reaction_pct,
            "post_loss_5s_recoveries_count": immediate_recovery_count,
            "post_loss_5s_recovery_pct": post_loss_recovery_5s_pct,
            "opponent_counter_attacks_conceded": int(len(opp_counters)),
            "opponent_counters_ending_in_shot": int(
                opp_counters["ended_in_shot"].sum()
            )
            if not opp_counters.empty
            else 0,
        }

    @classmethod
    def compute_midfield_control(
        cls, df_events: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        E. Calcula métricas de Controle Territorial de Meio-Campo:
        - Field Tilt (% de passes no terço final da partida pertencentes à equipe)
        - Dominância do Terço Médio (40 <= x < 80)
        - Retenção de passe sob pressão adversária (Press Resistance)
        - Jogadores com maior volume de distribuição no setor de meio-campo
        """
        team_passes = df_events[
            (df_events["team_name"] == target_team) & (df_events["type_name"] == "Pass")
        ]
        opp_passes = df_events[
            (df_events["team_name"] != target_team) & (df_events["type_name"] == "Pass")
        ]

        # Field Tilt: razão de passes no terço final (x >= 80)
        team_final_third_passes = int((team_passes["x"] >= 80.0).sum())
        opp_final_third_passes = int((opp_passes["x"] >= 80.0).sum())
        total_ft_passes = max(team_final_third_passes + opp_final_third_passes, 1)
        field_tilt_pct = round((team_final_third_passes / total_ft_passes) * 100.0, 2)

        # Controle do Terço Médio (40 <= x < 80)
        team_mid_passes = team_passes[
            (team_passes["x"] >= 40.0) & (team_passes["x"] < 80.0)
        ]
        opp_mid_passes = opp_passes[
            (opp_passes["x"] >= 40.0) & (opp_passes["x"] < 80.0)
        ]
        midfield_share_pct = round(
            (
                len(team_mid_passes)
                / max(len(team_mid_passes) + len(opp_mid_passes), 1)
            )
            * 100.0,
            2,
        )

        # Resistência à Pressão (Passes completos quando under_pressure == 1)
        pressured_passes = team_passes[team_passes["under_pressure"] == 1]
        n_press_passes = int(len(pressured_passes))
        press_resistance_pct = (
            round(
                (pressured_passes["is_pass_completed"].sum() / n_press_passes) * 100.0,
                2,
            )
            if n_press_passes > 0
            else 0.0
        )

        top_midfield_distributors = (
            team_mid_passes["player_name"].dropna().value_counts().head(3).to_dict()
        )

        return {
            "field_tilt_pct": field_tilt_pct,
            "midfield_possession_share_pct": midfield_share_pct,
            "pressured_passes_count": n_press_passes,
            "press_resistance_completion_pct": press_resistance_pct,
            "top_midfield_controllers": top_midfield_distributors,
        }

    @classmethod
    def compute_set_pieces(
        cls, df_events: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        F. Calcula métricas de Bolas Paradas (Escanteios e Faltas):
        - Classifica zona de destino dos escanteios (1ª Trave, Central/Marca do Pênalti, 2ª Trave, Curto)
        - Taxa de primeiro contato em escanteios ofensivos e defensivos
        """
        team_ev = df_events[df_events["team_name"] == target_team]
        opp_ev = df_events[df_events["team_name"] != target_team]

        def _classify_corner_zones(corners_df: pd.DataFrame) -> Dict[str, int]:
            zones = {
                "Primeira Trave (Near Post)": 0,
                "Zona Central / Pequena Área": 0,
                "Segunda Trave (Far Post)": 0,
                "Escanteio Curto / Fora da Área": 0,
            }
            for _, r in corners_df.iterrows():
                ex, ey = r.get("end_x", np.nan), r.get("end_y", np.nan)
                sy = r.get("y", 0.0)
                if pd.isna(ex) or pd.isna(ey) or ex < 102.0:
                    zones["Escanteio Curto / Fora da Área"] += 1
                    continue
                # Distância lateral relativa ao canto cobrado (y=0 ou y=80)
                dist_from_corner_side = abs(ey - sy)
                if dist_from_corner_side < 36.0:
                    zones["Primeira Trave (Near Post)"] += 1
                elif dist_from_corner_side <= 44.0:
                    zones["Zona Central / Pequena Área"] += 1
                else:
                    zones["Segunda Trave (Far Post)"] += 1
            return zones

        off_corners = team_ev[
            (team_ev["type_name"] == "Pass")
            & (team_ev["pass_type_name"] == "Corner")
        ]
        def_corners = opp_ev[
            (opp_ev["type_name"] == "Pass")
            & (opp_ev["pass_type_name"] == "Corner")
        ]

        off_corner_shots = team_ev[
            (team_ev["type_name"] == "Shot")
            & (team_ev["play_pattern_name"] == "From Corner")
        ]
        def_corner_shots = opp_ev[
            (opp_ev["type_name"] == "Shot")
            & (opp_ev["play_pattern_name"] == "From Corner")
        ]

        return {
            "offensive_corners_count": int(len(off_corners)),
            "offensive_corners_first_contact_won": int(
                off_corners["is_pass_completed"].sum()
            ),
            "offensive_corner_target_zones": _classify_corner_zones(off_corners),
            "shots_generated_from_corners": int(len(off_corner_shots)),
            "defensive_corners_faced": int(len(def_corners)),
            "defensive_corner_target_zones_faced": _classify_corner_zones(def_corners),
            "shots_conceded_from_corners": int(len(def_corner_shots)),
        }

    @classmethod
    def generate_full_match_tactical_summary(
        cls, df_events: pd.DataFrame, df_chains: pd.DataFrame, target_team: str
    ) -> Dict[str, Any]:
        """
        Executa todas as 6 dimensões táticas para a equipe selecionada e retorna
        um pacote consolidado pronto para o Motor de Inteligência Tática (Dia 9).
        """
        return {
            "team_name": target_team,
            "defensive_organization": cls.compute_defensive_organization(
                df_events, df_chains, target_team
            ),
            "offensive_organization": cls.compute_offensive_organization(
                df_events, df_chains, target_team
            ),
            "offensive_transition": cls.compute_offensive_transition(
                df_events, df_chains, target_team
            ),
            "defensive_transition": cls.compute_defensive_transition(
                df_events, df_chains, target_team
            ),
            "midfield_control": cls.compute_midfield_control(df_events, target_team),
            "set_pieces": cls.compute_set_pieces(df_events, target_team),
        }


if __name__ == "__main__":
    import json
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.preprocessing.event_cleaner import EventPreprocessor

    print("=" * 78)
    print("TACTICAL INTELLIGENCE LAB - MOTOR DE MÉTRICAS POR FASE DO JOGO (DIA 3)")
    print("=" * 78)

    loader = StatsBombDataLoader()
    match_id = 3869685  # Final Copa 2022: Argentina vs França

    raw_df = loader.ingest_match_events(match_id)
    enriched_df = EventPreprocessor.process_match_events(raw_df)
    chains_df = EventPreprocessor.build_possession_chains(enriched_df)

    for team in enriched_df["team_name"].unique():
        summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
            enriched_df, chains_df, team
        )
        d_org = summary["defensive_organization"]
        o_org = summary["offensive_organization"]
        o_trans = summary["offensive_transition"]
        d_trans = summary["defensive_transition"]
        mid = summary["midfield_control"]
        sp = summary["set_pieces"]

        print(f"\n======================================================================")
        print(f"RELATÓRIO NUMÉRICO DE FASES DO JOGO: {team.upper()}")
        print(f"======================================================================")
        print(
            f"[A. ORGANIZAÇÃO DEFENSIVA]\n"
            f"  * PPDA: {d_org['ppda']} ({d_org['ppda_numerator_opp_passes']} passes adv. / {d_org['ppda_denominator_def_actions']} ações de pressão)\n"
            f"  * Altura Média do Engajamento: {d_org['avg_defensive_engagement_height_m']} m ({d_org['block_profile']})\n"
            f"  * Corredor Defensivo Mais Vulnerável: {d_org['most_vulnerable_defensive_sector']}\n"
            f"  * Inversões de Jogo Enfrentadas: {d_org['switches_completed_by_opponent']}/{d_org['switches_faced']} concluídas pelo adversário ({d_org['switch_conceded_rate_pct']}%)"
        )
        print(
            f"[B. ORGANIZAÇÃO OFENSIVA]\n"
            f"  * Saída de Bola Curta no Terço Defensivo: {o_org['short_buildup_ratio_pct']}% (Acerto: {o_org['buildup_completion_pct']}% | Perdas no 1º terço: {o_org['buildup_turnovers_in_own_third']})\n"
            f"  * Corredor Preferencial de Progressão: {o_org['preferred_attack_corridor']}\n"
            f"  * Entradas na Zona 14: {o_org['zone_14_entries']} | Entradas na Grande Área: {o_org['penalty_box_entries']} | xG Total: {o_org['total_xg']}"
        )
        print(
            f"[C & D. TRANSIÇÕES]\n"
            f"  * Velocidade Direta de Progressão: {o_trans['overall_direct_speed_m_s']} m/s | Contra-Ataques: {o_trans['counter_attacks_count']} (Eficiência: {o_trans['counter_efficiency_pct']}%)\n"
            f"  * Reação Pós-Perda em 5s (Gegenpressing): {d_trans['post_loss_5s_press_reaction_pct']}% ({d_trans['post_loss_5s_press_reaction_count']}/{d_trans['turnovers_in_attacking_half']} perdas altas)"
        )
        print(
            f"[E & F. MEIO-CAMPO E BOLAS PARADAS]\n"
            f"  * Field Tilt (Domínio Territorial no Terço Final): {mid['field_tilt_pct']}% | Resistência à Pressão: {mid['press_resistance_completion_pct']}%\n"
            f"  * Escanteios Ofensivos: {sp['offensive_corners_count']} (Chutes gerados: {sp['shots_generated_from_corners']}) | Zonas Alvo: {sp['offensive_corner_target_zones']}"
        )

        # Salva JSON auditado de métricas em data/processed/
        safe_name = team.lower().replace(" ", "_")
        out_json = f"data/processed/metrics_{match_id}_{safe_name}.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"  -> Pacote JSON salvo em: {out_json}")