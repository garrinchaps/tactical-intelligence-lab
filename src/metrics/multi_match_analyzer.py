"""
Módulo de Análise Longitudinal de Múltiplas Partidas (Camada 3.I)
Analisa uma sequência histórica de N partidas de uma equipe para identificar
padrões táticos recorrentes, calcular estabilidade estatística (Média, Desvio-Padrão,
Coeficiente de Variação) e separar deficiências crônicas de ruído de jogo único.
"""

from typing import Any, Dict, List
import numpy as np
import pandas as pd
from src.preprocessing.event_cleaner import EventPreprocessor
from src.metrics.tactical_metrics import TacticalMetricsEngine


class MultiMatchTrendAnalyzer:
    """
    Avalia a consistência de indicadores táticos ao longo de várias partidas.
    Classifica cada comportamento como:
    - PADRÃO CRÔNICO RECORRENTE (Presente em >= 66.7% dos jogos)
    - TENDÊNCIA INTERMITENTE / CONTEXTUAL (Presente entre 35% e 66.6% dos jogos)
    - EVENTO ISOLADO (Presente em <= 1 jogo ou < 35% da amostra)
    """

    @classmethod
    def analyze_team_across_matches(
        cls,
        matches_events_map: Dict[int, pd.DataFrame],
        target_team: str,
    ) -> Dict[str, Any]:
        """
        Recebe um dicionário {match_id: df_events_raw_ou_enriched} contendo N partidas
        em que `target_team` atuou, extrai o sumário tático de cada jogo e consolida
        as tendências longitudinais.
        """
        per_match_records: List[Dict[str, Any]] = []

        for match_id, df_ev in matches_events_map.items():
            if df_ev.empty or target_team not in df_ev["team_name"].unique():
                continue

            if "is_progressive_action" not in df_ev.columns:
                enriched = EventPreprocessor.process_match_events(df_ev)
            else:
                enriched = df_ev

            chains = EventPreprocessor.build_possession_chains(enriched)
            summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
                enriched, chains, target_team
            )

            opponents = [
                t for t in enriched["team_name"].unique() if t != target_team
            ]
            opponent_name = opponents[0] if opponents else "Opponent"

            d_org = summary["defensive_organization"]
            o_org = summary["offensive_organization"]
            o_tr = summary["offensive_transition"]
            d_tr = summary["defensive_transition"]
            mid = summary["midfield_control"]

            per_match_records.append(
                {
                    "match_id": int(match_id),
                    "opponent": str(opponent_name),
                    "ppda": float(d_org["ppda"]),
                    "def_height_m": float(d_org["avg_defensive_engagement_height_m"]),
                    "most_vulnerable_def_sector": str(
                        d_org["most_vulnerable_defensive_sector"]
                    ),
                    "switch_conceded_rate_pct": float(d_org["switch_conceded_rate_pct"]),
                    "switches_completed_by_opp": int(
                        d_org["switches_completed_by_opponent"]
                    ),
                    "xg_conceded": float(d_org["xg_conceded"]),
                    "short_buildup_pct": float(o_org["short_buildup_ratio_pct"]),
                    "buildup_turnovers": int(o_org["buildup_turnovers_in_own_third"]),
                    "preferred_attack_corridor": str(
                        o_org["preferred_attack_corridor"]
                    ),
                    "zone_14_entries": int(o_org["zone_14_entries"]),
                    "box_entries": int(o_org["penalty_box_entries"]),
                    "xg_created": float(o_org["total_xg"]),
                    "direct_speed_m_s": float(o_tr["overall_direct_speed_m_s"]),
                    "counter_attacks": int(o_tr["counter_attacks_count"]),
                    "gegenpress_5s_pct": float(d_tr["post_loss_5s_press_reaction_pct"]),
                    "opp_counters_conceded": int(
                        d_tr["opponent_counter_attacks_conceded"]
                    ),
                    "field_tilt_pct": float(mid["field_tilt_pct"]),
                    "press_resistance_pct": float(
                        mid["press_resistance_completion_pct"]
                    ),
                }
            )

        df_history = pd.DataFrame(per_match_records)
        n_matches = int(len(df_history))

        if n_matches == 0:
            return {
                "team_name": target_team,
                "matches_analyzed": 0,
                "status": "NO_MATCHES_FOUND",
            }

        # 1. Estatísticas de Estabilidade Contínua (Média, Desvio-Padrão e Coeficiente de Variação)
        continuous_cols = [
            "ppda",
            "def_height_m",
            "switch_conceded_rate_pct",
            "short_buildup_pct",
            "zone_14_entries",
            "box_entries",
            "xg_created",
            "xg_conceded",
            "gegenpress_5s_pct",
            "field_tilt_pct",
            "press_resistance_pct",
        ]

        stability_stats: Dict[str, Dict[str, Any]] = {}
        for col in continuous_cols:
            mean_val = float(df_history[col].mean())
            std_val = float(df_history[col].std(ddof=0)) if n_matches > 1 else 0.0
            cv = (std_val / abs(mean_val)) if abs(mean_val) > 1e-5 else 0.0
            stability_stats[col] = {
                "mean": round(mean_val, 2),
                "std": round(std_val, 2),
                "min": round(float(df_history[col].min()), 2),
                "max": round(float(df_history[col].max()), 2),
                "coefficient_of_variation": round(cv, 3),
                "is_structural_constant": bool(cv < 0.25 and n_matches >= 2),
            }

        # 2. Detecção de Padrões Categóricos e Problemas Recorrentes vs. Isolados
        def _classify_recurrence(occurrences: int, total: int) -> str:
            ratio = occurrences / max(total, 1)
            if total >= 2 and ratio >= 0.66:
                return "PADRÃO CRÔNICO RECORRENTE"
            if total >= 2 and ratio >= 0.40:
                return "TENDÊNCIA INTERMITENTE / CONTEXTUAL"
            return "EVENTO ISOLADO"

        # Corredor defensivo mais vulnerável ao longo dos jogos
        vuln_counts = df_history["most_vulnerable_def_sector"].value_counts()
        top_vuln_sector = str(vuln_counts.index[0])
        top_vuln_occ = int(vuln_counts.iloc[0])

        # Corredor ofensivo preferencial ao longo dos jogos
        att_counts = df_history["preferred_attack_corridor"].value_counts()
        top_att_corridor = str(att_counts.index[0])
        top_att_occ = int(att_counts.iloc[0])

        # Verifica vulnerabilidade a inversões de jogo (>= 65% de sucesso adversário em >= 4 inversões)
        high_switch_vuln_matches = int(
            (
                (df_history["switch_conceded_rate_pct"] >= 65.0)
                & (df_history["switches_completed_by_opp"] >= 4)
            ).sum()
        )

        # Verifica perdas recorrentes na saída de bola no próprio terço (>= 5 turnovers no 1º terço)
        buildup_error_matches = int((df_history["buildup_turnovers"] >= 5).sum())

        findings: List[Dict[str, Any]] = [
            {
                "pattern_type": "Vulnerabilidade Espacial Defensiva",
                "sector_or_metric": top_vuln_sector,
                "matches_observed": top_vuln_occ,
                "total_matches": n_matches,
                "recurrence_rate_pct": round((top_vuln_occ / n_matches) * 100.0, 2),
                "classification": _classify_recurrence(top_vuln_occ, n_matches),
                "tactical_explanation": (
                    f"Em {top_vuln_occ} das {n_matches} partidas analisadas ({round((top_vuln_occ / n_matches) * 100.0, 1)}%), "
                    f"o setor que mais cedeu ações progressivas ao adversário foi '{top_vuln_sector}'."
                ),
            },
            {
                "pattern_type": "Vetor Preferencial de Construção Ofensiva",
                "sector_or_metric": top_att_corridor,
                "matches_observed": top_att_occ,
                "total_matches": n_matches,
                "recurrence_rate_pct": round((top_att_occ / n_matches) * 100.0, 2),
                "classification": _classify_recurrence(top_att_occ, n_matches),
                "tactical_explanation": (
                    f"Em {top_att_occ} das {n_matches} partidas ({round((top_att_occ / n_matches) * 100.0, 1)}%), "
                    f"a equipe concentrou sua progressão principal pelo '{top_att_corridor}'."
                ),
            },
            {
                "pattern_type": "Defesa de Inversões de Jogo (Switches of Play)",
                "sector_or_metric": f"Média de {stability_stats['switch_conceded_rate_pct']['mean']}% de acerto cedido em inversões",
                "matches_observed": high_switch_vuln_matches,
                "total_matches": n_matches,
                "recurrence_rate_pct": round(
                    (high_switch_vuln_matches / n_matches) * 100.0, 2
                ),
                "classification": _classify_recurrence(
                    high_switch_vuln_matches, n_matches
                ),
                "tactical_explanation": (
                    f"A equipe permitiu alta taxa de sucesso (>=65%) em inversões longas do adversário em "
                    f"{high_switch_vuln_matches} de {n_matches} jogos, indicando dificuldade de basculação horizontal do lado oposto."
                ),
            },
            {
                "pattern_type": "Risco na Saída de Bola (1º Terço)",
                "sector_or_metric": f"Média de {round(float(df_history['buildup_turnovers'].mean()), 1)} turnovers/jogo no terço defensivo",
                "matches_observed": buildup_error_matches,
                "total_matches": n_matches,
                "recurrence_rate_pct": round(
                    (buildup_error_matches / n_matches) * 100.0, 2
                ),
                "classification": _classify_recurrence(
                    buildup_error_matches, n_matches
                ),
                "tactical_explanation": (
                    f"A equipe sofreu 5 ou mais perdas de posse no próprio terço defensivo em "
                    f"{buildup_error_matches} de {n_matches} jogos (Saída curta média = {stability_stats['short_buildup_pct']['mean']}%)."
                ),
            },
        ]

        return {
            "team_name": target_team,
            "matches_analyzed": n_matches,
            "status": "OK",
            "per_match_table": df_history.to_dict(orient="records"),
            "longitudinal_stability_stats": stability_stats,
            "pattern_diagnostics": findings,
        }


if __name__ == "__main__":
    import json
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.metrics.player_evaluator import PlayerTacticalEvaluator

    print("=" * 80)
    print("TACTICAL INTELLIGENCE LAB - ANÁLISE INDIVIDUAL, SUBSTITUIÇÕES E MÚLTIPLOS JOGOS (DIA 8)")
    print("=" * 80)

    loader = StatsBombDataLoader()

    # 1. Avaliação Individual e Substituições na Final (3869685)
    final_id = 3869685
    raw_final = loader.ingest_match_events(final_id)
    enriched_final = EventPreprocessor.process_match_events(raw_final)

    print("\n[PARTE 1: AVALIAÇÃO INDIVIDUAL E RECOMENDAÇÃO DE SUBSTITUIÇÕES - ARGENTINA]")
    arg_players = PlayerTacticalEvaluator.evaluate_team_players(
        enriched_final, "Argentina"
    )
    print(
        arg_players[
            [
                "player_name",
                "position_name",
                "passes_completed",
                "progressive_actions",
                "line_breaking_passes",
                "xt_generated",
                "ball_recoveries",
                "tactical_impact_score",
            ]
        ]
        .head(6)
        .to_string(index=False)
    )

    # Comparação Head-to-Head de dois meio-campistas da Argentina
    h2h = PlayerTacticalEvaluator.compare_players_head_to_head(
        arg_players,
        "Enzo Fernandez",
        "Rodrigo Javier De Paul",
    )
    if h2h["status"] == "OK":
        print(f"\n  [Comparação Direta de Meio-Campistas]:")
        print(f"    -> {h2h['player_a']}: {h2h['player_a_inferred_role']}")
        print(f"    -> {h2h['player_b']}: {h2h['player_b_inferred_role']}")

    subs_report = PlayerTacticalEvaluator.recommend_tactical_substitutions(
        enriched_final, "Argentina"
    )
    print(f"\n  [Prescrição Tática de Substituições (Baseada em Degradação Pós-60 min)]:")
    for rec in subs_report["recommended_substitutions"]:
        print(f"    -> Candidato a sair: {rec['candidate_out']} ({rec['position']}) | Prioridade: {rec['priority_score']}")
        for r in rec["tactical_reasons"]:
            print(f"       * Motivo: {r}")
        print(f"       * Perfil recomendado para entrar: {rec['ideal_replacement_profile']}")
        print(f"       * Risco estrutural: {rec['structural_risks_of_substitution'][0]}")

    # 2. Análise Longitudinal de Múltiplas Partidas da Argentina (Quartas, Semifinal e Final)
    arg_match_ids = [3869321, 3869519, 3869685]
    matches_map = {}
    for mid in arg_match_ids:
        matches_map[mid] = loader.ingest_match_events(mid)

    print("\n" + "=" * 80)
    print("[PARTE 2: ANÁLISE LONGITUDINAL DE MÚLTIPLAS PARTIDAS - ARGENTINA (3 JOGOS)]")
    print("=" * 80)
    trend_report = MultiMatchTrendAnalyzer.analyze_team_across_matches(
        matches_map, target_team="Argentina"
    )

    for diag in trend_report["pattern_diagnostics"]:
        print(
            f"  * [{diag['classification']}] {diag['pattern_type']}: {diag['tactical_explanation']}"
        )

    with open(
        "data/processed/multi_match_trends_argentina.json", "w", encoding="utf-8"
    ) as f:
        json.dump(trend_report, f, ensure_ascii=False, indent=2)
    print("\n[OK] Dia 8 concluído! Relatório longitudinal salvo em: data/processed/multi_match_trends_argentina.json")