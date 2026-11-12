"""
Motor Central de Inteligência Tática e Classificador de Evidências (Camada 3 - Tactical Engine)
Combina métricas numéricas, grafos, xT, clusters e Machine Learning em diagnósticos
táticos estruturados com rastreabilidade completa e classificação da força da evidência.
"""

from typing import Any, Dict, List, Optional
import pandas as pd
from src.geometry.pitch_zones import PitchGeometry
from src.metrics.tactical_metrics import TacticalMetricsEngine
from src.networks.pass_network import PassingNetworkAnalyzer
from src.metrics.xt_model import ExpectedThreatModel
from src.machine_learning.clustering import SpatialTacticalClustering
from src.machine_learning.supervised import PossessionDangerClassifier


class TacticalDiagnosticEngine:
    """
    Motor central que traduz indicadores matemáticos em laudos táticos estruturados
    completos, garantindo o rigor científico e proibindo a invenção de dados.
    """

    @staticmethod
    def classify_evidence_strength(sample_size: int, consistency_score: float = 1.0) -> str:
        """
        Classifica a robustez da evidência estatística:
        - FORTE: Amostra robusta (N >= 10) e alta consistência.
        - MODERADA: Amostra intermediária (5 <= N < 10) ou tendência observada.
        - LIMITADA: Amostra baixa (N < 5) ou dados restritos.
        """
        if sample_size >= 10 and consistency_score >= 0.7:
            return "FORTE"
        elif sample_size >= 5:
            return "MODERADA"
        else:
            return "LIMITADA"

    @classmethod
    def generate_comprehensive_diagnostics(
        cls,
        df_events: pd.DataFrame,
        df_chains: pd.DataFrame,
        target_team: str,
        classifier: Optional[PossessionDangerClassifier] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executa uma bateria completa de varredura tática sobre a partida e retorna
        uma lista de objetos de diagnóstico auditados.
        """
        diagnostics: List[Dict[str, Any]] = []

        # 1. Executa módulos de suporte
        tactical_summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
            df_events, df_chains, target_team
        )
        network_res = PassingNetworkAnalyzer.build_pass_network(
            df_events, target_team, until_first_sub=True
        )
        xt_enriched = ExpectedThreatModel.enrich_events_with_xt(df_events)
        xt_summary = ExpectedThreatModel.compute_team_xt_summary(xt_enriched, target_team)
        cluster_res = SpatialTacticalClustering.analyze_turnover_clusters(df_events, target_team)

        d_org = tactical_summary["defensive_organization"]
        o_org = tactical_summary["offensive_organization"]
        d_tr = tactical_summary["defensive_transition"]
        o_tr = tactical_summary["offensive_transition"]
        gm = network_res["graph_metrics"]

        # =====================================================================
        # DIAGNÓSTICO 1: Organização Defensiva e Vulnerabilidade por Corredor
        # =====================================================================
        vulnerable_sector = d_org["most_vulnerable_defensive_sector"]
        sec_data = d_org["corridor_vulnerability_breakdown"].get(vulnerable_sector, {})
        n_prog_conceded = sec_data.get("progressive_actions_conceded", 0)
        box_conceded = sec_data.get("box_entries_conceded", 0)

        ev_strength_def = cls.classify_evidence_strength(n_prog_conceded)

        diagnostics.append(
            {
                "problem_title": f"Exposição Recorrente no {vulnerable_sector}",
                "phase_of_play": "Organização Defensiva",
                "team_name": target_team,
                "pitch_zone": vulnerable_sector,
                "frequency_pct": sec_data.get("share_of_opponent_progression_pct", 0.0),
                "sample_size": n_prog_conceded,
                "evidence_strength": ev_strength_def,
                "tactical_interpretation": (
                    f"Durante a fase defensiva com bloco de perfil '{d_org['block_profile']}' (PPDA = {d_org['ppda']}), "
                    f"a equipe apresentou abertura recorrente no {vulnerable_sector}. O adversário canalizou "
                    f"{n_prog_conceded} ações progressivas e {box_conceded} entradas na grande área por este setor."
                ),
                "probable_consequence": "Facilidade do adversário em progredir pelo corredor e gerar finalizações cruzadas para a segunda trave.",
                "recommendation_plan_a": "Recrutar o volante do lado da bola para cobertura preventiva mais rápida, encurtando a distância entre o lateral e o zagueiro.",
                "recommendation_alternative_b": "Ajustar o bloco para uma basculação mais compacta em linha de 4 ou 5, evitando que o ala/ponta adversário receba com tempo para virar o corpo.",
                "recommendation_risks": "Exposição temporária do lado oposto do campo caso a basculação lateral seja lenta.",
                "data_limitations": "Análise baseada em dados de eventos e coordenadas estritas; ausência de tracking contínuo de 22 jogadores impede medir exatamente a distância em metros do enquadramento do corpo.",
            }
        )

        # =====================================================================
        # DIAGNÓSTICO 2: Construtor / Pivô da Saída de Bola (Alvo de Pressão)
        # =====================================================================
        primary_bridge = gm.get("primary_bridge_player_betweenness", "N/A")
        bridge_score = gm.get("primary_bridge_score", 0.0)
        sample_bridge = int(gm.get("total_completed_passes_in_network", 0))

        diagnostics.append(
            {
                "problem_title": f"Concentração da Saída de Bola em '{primary_bridge}'",
                "phase_of_play": "Organização Ofensiva / Saída de Bola",
                "team_name": target_team,
                "pitch_zone": "Terço Defensivo / Eixo Central",
                "frequency_pct": gm.get("max_player_pass_share_pct", 0.0),
                "sample_size": sample_bridge,
                "evidence_strength": "FORTE" if sample_bridge >= 30 else "MODERADA",
                "tactical_interpretation": (
                    f"O atleta '{primary_bridge}' detém a maior Centralidade de Intermediação ({bridge_score}) "
                    f"da rede de passes, funcionando como o pivô obrigatório de conexão entre a defesa e o meio-campo."
                ),
                "probable_consequence": "Se o adversário encaixar uma marcação pressão individual sobre este jogador, a saída de bola da equipe colapsará.",
                "recommendation_plan_a": "Establiccer linhas de passe de apoio em diagonal (com o zagueiro e o lateral) para oferecer opção de escape caso o pivô seja encaixotado.",
                "recommendation_alternative_b": "Utilizar inversões rápidas de bola para o lado oposto antes que a pressão adversária compacte sobre o principal distribuidor.",
                "recommendation_risks": "Perda de fluidez na circulação central caso os apoios demorem a se aproximar.",
                "data_limitations": "Rede construída com base nos passes completos até a primeira substituição.",
            }
        )

        # =====================================================================
        # DIAGNÓSTICO 3: Zonas Críticas de Perda de Posse (Turnovers)
        # =====================================================================
        highest_risk_c = cluster_res.get("highest_risk_exposure_cluster")
        if highest_risk_c and highest_risk_c.get("local_radius_touches_denominator", 0) >= 5:
            turn_count = highest_risk_c["turnovers_in_cluster"]
            diagnostics.append(
                {
                    "problem_title": f"Vulnerabilidade Crítica de Perda na Zona {highest_risk_c['zone_18']} ({highest_risk_c['tactical_third']} - {highest_risk_c['tactical_corridor']})",
                    "phase_of_play": "Transição Defensiva / Construção",
                    "team_name": target_team,
                    "pitch_zone": f"Zona {highest_risk_c['zone_18']} ({highest_risk_c['tactical_corridor']})",
                    "frequency_pct": highest_risk_c["turnover_rate_per_touch_pct"],
                    "sample_size": turn_count,
                    "evidence_strength": cls.classify_evidence_strength(turn_count),
                    "tactical_interpretation": (
                        f"O algoritmo K-Means associado à exposição territorial identificou que a equipe apresenta "
                        f"uma taxa de erro de {highest_risk_c['turnover_rate_per_touch_pct']}% por toque na {highest_risk_c['tactical_third']} "
                        f"({highest_risk_c['tactical_corridor']}), com {highest_risk_c['under_pressure_rate_pct']}% das ações sob pressão direta."
                    ),
                    "probable_consequence": "Exposição a contra-ataques fulminantes do adversário em zonas de construção vulneráveis.",
                    "recommendation_plan_a": "Exigir jogo mais direto ou passes de segurança quando a equipe estiver sob forte pressão nestas coordenadas.",
                    "recommendation_alternative_b": "Garantir superioridade numérica de apoio (terceiro homem) para oferecer linha de escape rápida.",
                    "recommendation_risks": "Redução momentânea do volume de posse curta no setor.",
                    "data_limitations": "Clusterização baseada em coordenadas (x, y) de perdas registradas na partida.",
                }
            )

        return diagnostics


if __name__ == "__main__":
    import json
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.preprocessing.event_cleaner import EventPreprocessor

    print("=" * 78)
    print("TACTICAL INTELLIGENCE LAB - MOTOR DE INTELIGÊNCIA TÁTICA (DIAGNÓSTICOS) (DIA 9)")
    print("=" * 78)

    loader = StatsBombDataLoader()
    match_id = 3869685  # Final Copa 2022: Argentina vs França

    raw_df = loader.ingest_match_events(match_id)
    enriched_df = EventPreprocessor.process_match_events(raw_df)
    chains_df = EventPreprocessor.build_possession_chains(enriched_df)

    for team in ["Argentina", "França"]:
        diags = TacticalDiagnosticEngine.generate_comprehensive_diagnostics(
            enriched_df, chains_df, team
        )

        print(f"\n======================================================================")
        print(f"DIAGNÓSTICOS TÁTICOS AUDITADOS: {team.upper()}")
        print(f"======================================================================")
        for i, d in enumerate(diags, 1):
            print(f"  [{i}] {d['problem_title']}")
            print(f"      * Fase / Setor: {d['phase_of_play']} | Região: {d['pitch_zone']}")
            print(f"      * Grau de Evidência: [{d['evidence_strength']}] (N = {d['sample_size']} ocorrências)")
            print(f"      * Interpretação: {d['tactical_interpretation']}")
            print(f"      * Recomendação (Plano A): {d['recommendation_plan_a']}\n")

        safe_name = team.lower().replace(" ", "_")
        with open(
            f"data/processed/diagnostics_{match_id}_{safe_name}.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(diags, f, ensure_ascii=False, indent=2)

    print("[OK] Dia 9 concluído! Diagnósticos táticos salvos em data/processed/")