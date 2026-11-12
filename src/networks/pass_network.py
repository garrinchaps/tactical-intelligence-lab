"""
Módulo de Teoria dos Grafos e Redes de Passes (Camada 2 - Redes Complexas)
Modela a circulação de bola de uma equipe como um grafo direcionado e ponderado G = (V, E, W).
Calcula métricas topológicas via NetworkX para identificar organizadores, gargalos de saída
de bola, triangulações e assimetrias posicionais.
"""

from typing import Any, Dict, List, Optional, Tuple
import networkx as nx
import numpy as np
import pandas as pd


class PassingNetworkAnalyzer:
    """
    Constrói e analisa a rede de passes de uma equipe a partir dos eventos enriquecidos.
    Suporta corte automático na 1ª substituição (para preservar os 11 titulares na estrutura)
    ou análise da partida completa.
    """

    @staticmethod
    def _get_first_substitution_minute(
        df_events: pd.DataFrame, target_team: str
    ) -> float:
        """
        Retorna o tempo em segundos da primeira substituição da equipe (ou o fim do jogo
        caso não haja substituições registradas).
        """
        team_subs = df_events[
            (df_events["team_name"] == target_team)
            & (df_events["type_name"] == "Substitution")
        ]
        if team_subs.empty:
            return float(df_events["time_seconds"].max() + 1.0)
        return float(team_subs["time_seconds"].min())

    @classmethod
    def build_pass_network(
        cls,
        df_events: pd.DataFrame,
        target_team: str,
        until_first_sub: bool = True,
        min_pass_count: int = 2,
    ) -> Dict[str, Any]:
        """
        Constrói o grafo direcionado de passes completos da equipe `target_team`
        e retorna:
        - nodes_df: DataFrame com cada jogador, posição média (x, y) e métricas de centralidade.
        - edges_df: DataFrame com os pares (passer -> recipient), contagem de passes e progressão média.
        - graph_metrics: Indicadores coletivos da rede (densidade, reciprocidade, clustering, gargalo, assimetria).
        """
        team_ev = df_events[df_events["team_name"] == target_team].copy()
        if team_ev.empty:
            return cls._empty_network_response(target_team)

        cutoff_sec = (
            cls._get_first_substitution_minute(df_events, target_team)
            if until_first_sub
            else float(team_ev["time_seconds"].max() + 1.0)
        )
        # Se a primeira substituição ocorreu muito cedo (< 25 min por lesão), usa pelo menos 45 min
        if until_first_sub and cutoff_sec < 25.0 * 60.0:
            cutoff_sec = max(cutoff_sec, 45.0 * 60.0)

        window_ev = team_ev[team_ev["time_seconds"] <= cutoff_sec].copy()

        # Passes completos dentro da janela estrutural
        completed_passes = window_ev[
            (window_ev["type_name"] == "Pass")
            & (window_ev["is_pass_completed"] == 1)
            & (window_ev["player_name"].notna())
            & (window_ev["pass_recipient_name"].notna())
            & (window_ev["x"].notna())
            & (window_ev["y"].notna())
        ].copy()

        if completed_passes.empty:
            return cls._empty_network_response(target_team)

        # 1. Posição média (x, y) de cada jogador baseada nos passes originados e recebidos
        origin_coords = completed_passes[
            ["player_name", "position_name", "x", "y"]
        ].rename(columns={"player_name": "player"})

        recv_coords = completed_passes[
            ["pass_recipient_name", "end_x", "end_y"]
        ].rename(
            columns={
                "pass_recipient_name": "player",
                "end_x": "x",
                "end_y": "y",
            }
        )
        recv_coords["position_name"] = None

        all_touches = pd.concat([origin_coords, recv_coords], ignore_index=True)
        all_touches = all_touches.dropna(subset=["player", "x", "y"])

        # Mantém os 11 jogadores com maior participação na janela se until_first_sub=True
        touch_counts = all_touches["player"].value_counts()
        active_players = (
            touch_counts.head(11).index.tolist()
            if until_first_sub
            else touch_counts.index.tolist()
        )

        all_touches = all_touches[all_touches["player"].isin(active_players)]
        completed_passes = completed_passes[
            completed_passes["player_name"].isin(active_players)
            & completed_passes["pass_recipient_name"].isin(active_players)
        ]

        # Agrega coordenadas médias por jogador
        player_nodes = []
        for player_name in active_players:
            p_touches = all_touches[all_touches["player"] == player_name]
            p_passes_out = completed_passes[
                completed_passes["player_name"] == player_name
            ]
            p_passes_in = completed_passes[
                completed_passes["pass_recipient_name"] == player_name
            ]

            pos_series = p_touches["position_name"].dropna()
            role_name = str(pos_series.mode().iloc[0]) if not pos_series.empty else "Unknown"

            player_nodes.append(
                {
                    "player_name": str(player_name),
                    "position_name": role_name,
                    "avg_x": round(float(p_touches["x"].mean()), 2),
                    "avg_y": round(float(p_touches["y"].mean()), 2),
                    "std_x": round(float(p_touches["x"].std(ddof=0)), 2),
                    "std_y": round(float(p_touches["y"].std(ddof=0)), 2),
                    "passes_made": int(len(p_passes_out)),
                    "passes_received": int(len(p_passes_in)),
                    "progressive_passes_made": int(
                        p_passes_out["is_progressive_action"].sum()
                    ),
                }
            )

        nodes_df = pd.DataFrame(player_nodes)

        # 2. Agrega arestas direcionadas (Passer -> Recipient)
        edges_grouped = (
            completed_passes.groupby(["player_name", "pass_recipient_name"], as_index=False)
            .agg(
                pass_count=("event_id", "count"),
                progressive_count=("is_progressive_action", "sum"),
                avg_length_m=("distance_meters", "mean"),
                avg_goal_progression_m=("goal_progression_meters", "mean"),
            )
            .rename(
                columns={
                    "player_name": "source",
                    "pass_recipient_name": "target",
                }
            )
        )
        # Remove auto-passes eventuais e filtra pelo limiar mínimo para visualização/grafo
        edges_grouped = edges_grouped[
            edges_grouped["source"] != edges_grouped["target"]
        ].reset_index(drop=True)

        # 3. Constrói o Grafo Direcionado Ponderado no NetworkX
        G = nx.DiGraph()
        for _, nrow in nodes_df.iterrows():
            G.add_node(
                nrow["player_name"],
                avg_x=nrow["avg_x"],
                avg_y=nrow["avg_y"],
                position_name=nrow["position_name"],
            )

        for _, erow in edges_grouped.iterrows():
            w = int(erow["pass_count"])
            if w >= 1:
                # topological_distance = 1 / w (quanto mais passes entre a dupla, menor a distância topológica)
                G.add_edge(
                    erow["source"],
                    erow["target"],
                    weight=float(w),
                    topological_distance=1.0 / float(w),
                    progressive_count=int(erow["progressive_count"]),
                )

        # 4. Cálculo das Centralidades Topológicas no NetworkX
        if G.number_of_nodes() > 1 and G.number_of_edges() > 0:
            betweenness = nx.betweenness_centrality(
                G, weight="topological_distance", normalized=True
            )
            try:
                pagerank = nx.pagerank(G, weight="weight", max_iter=500)
            except Exception:
                pagerank = {n: 1.0 / G.number_of_nodes() for n in G.nodes()}

            # Coeficiente de clustering (triangulações ponderadas)
            undirected_G = G.to_undirected()
            clustering_dict = nx.clustering(undirected_G, weight="weight")
            avg_clustering = round(float(np.mean(list(clustering_dict.values()))), 4)
            density = round(float(nx.density(G)), 4)
            reciprocity = round(float(nx.reciprocity(G) or 0.0), 4)
        else:
            betweenness = {n: 0.0 for n in G.nodes()}
            pagerank = {n: 0.0 for n in G.nodes()}
            clustering_dict = {n: 0.0 for n in G.nodes()}
            avg_clustering, density, reciprocity = 0.0, 0.0, 0.0

        nodes_df["betweenness_centrality"] = nodes_df["player_name"].map(
            lambda p: round(float(betweenness.get(p, 0.0)), 4)
        )
        nodes_df["pagerank_centrality"] = nodes_df["player_name"].map(
            lambda p: round(float(pagerank.get(p, 0.0)), 4)
        )
        nodes_df["clustering_coeff"] = nodes_df["player_name"].map(
            lambda p: round(float(clustering_dict.get(p, 0.0)), 4)
        )
        nodes_df["total_involvement"] = (
            nodes_df["passes_made"] + nodes_df["passes_received"]
        )

        # Ordena jogadores por importância estrutural (PageRank + Betweenness)
        nodes_df = nodes_df.sort_values(
            by=["betweenness_centrality", "pagerank_centrality", "total_involvement"],
            ascending=False,
        ).reset_index(drop=True)

        # Adiciona coordenadas de origem e destino nas arestas para plotagem imediata (Dia 11)
        coord_map_x = dict(zip(nodes_df["player_name"], nodes_df["avg_x"]))
        coord_map_y = dict(zip(nodes_df["player_name"], nodes_df["avg_y"]))
        edges_filtered = edges_grouped[
            edges_grouped["pass_count"] >= min_pass_count
        ].copy()
        edges_filtered["source_x"] = edges_filtered["source"].map(coord_map_x)
        edges_filtered["source_y"] = edges_filtered["source"].map(coord_map_y)
        edges_filtered["target_x"] = edges_filtered["target"].map(coord_map_x)
        edges_filtered["target_y"] = edges_filtered["target"].map(coord_map_y)
        edges_filtered = edges_filtered.sort_values(
            by="pass_count", ascending=False
        ).reset_index(drop=True)

        # 5. Diagnóstico Estrutural e Identificação de Alvos Táticos
        primary_hub = str(nodes_df.iloc[0]["player_name"])
        primary_hub_bt = float(nodes_df.iloc[0]["betweenness_centrality"])

        # Organizador mais acionado por PageRank
        pr_sorted = nodes_df.sort_values("pagerank_centrality", ascending=False)
        primary_playmaker = str(pr_sorted.iloc[0]["player_name"])
        primary_playmaker_pr = float(pr_sorted.iloc[0]["pagerank_centrality"])

        # Índice de Centralização (Dependência de um único jogador):
        # Se um único atleta detém > 22% de todos os passes feitos pela equipe, há dependência estrutural
        total_team_passes = max(int(nodes_df["passes_made"].sum()), 1)
        max_player_pass_share_pct = round(
            (float(nodes_df["passes_made"].max()) / total_team_passes) * 100.0, 2
        )
        top_pass_volume_player = str(
            nodes_df.sort_values("passes_made", ascending=False).iloc[0]["player_name"]
        )

        # Assimetria Lateral da Rede (Centroide Y da equipe: < 37 = Esquerda, > 43 = Direita)
        weighted_y = float(
            np.average(nodes_df["avg_y"], weights=np.maximum(nodes_df["total_involvement"], 1))
        )
        if weighted_y < 36.5:
            lateral_bias = "Forte sobrecarga no lado esquerdo da construção"
        elif weighted_y > 43.5:
            lateral_bias = "Forte sobrecarga no lado direito da construção"
        else:
            lateral_bias = "Circulação horizontalmente balanceada"

        # Estimativa da Estrutura Posicional Real (excluindo o goleiro com menor avg_x)
        outfield_df = nodes_df.sort_values("avg_x").iloc[1:].copy() if len(nodes_df) >= 10 else nodes_df.copy()
        n_base = int((outfield_df["avg_x"] < 48.0).sum())
        n_mid = int(((outfield_df["avg_x"] >= 48.0) & (outfield_df["avg_x"] < 74.0)).sum())
        n_att = int((outfield_df["avg_x"] >= 74.0).sum())
        inferred_shape = f"{n_base}-{n_mid}-{n_att} (Em Posse)"

        top_combinations = []
        for _, r in edges_filtered.head(5).iterrows():
            top_combinations.append(
                {
                    "pair": f"{r['source']} -> {r['target']}",
                    "passes": int(r["pass_count"]),
                    "progressive_passes": int(r["progressive_count"]),
                }
            )

        graph_metrics = {
            "team_name": target_team,
            "analyzed_until_minute": round(cutoff_sec / 60.0, 1),
            "nodes_count": int(G.number_of_nodes()),
            "edges_count": int(G.number_of_edges()),
            "total_completed_passes_in_network": total_team_passes,
            "network_density": density,
            "network_reciprocity": reciprocity,
            "avg_clustering_coefficient": avg_clustering,
            "inferred_positional_structure": inferred_shape,
            "team_weighted_centroid_y": round(weighted_y, 2),
            "lateral_asymmetry_diagnosis": lateral_bias,
            "primary_bridge_player_betweenness": primary_hub,
            "primary_bridge_score": primary_hub_bt,
            "primary_gravity_playmaker_pagerank": primary_playmaker,
            "primary_playmaker_pagerank_score": primary_playmaker_pr,
            "highest_volume_distributor": top_pass_volume_player,
            "max_player_pass_share_pct": max_player_pass_share_pct,
            "top_5_pass_combinations": top_combinations,
        }

        return {
            "nodes_df": nodes_df,
            "edges_df": edges_filtered,
            "graph_metrics": graph_metrics,
        }

    @staticmethod
    def _empty_network_response(target_team: str) -> Dict[str, Any]:
        return {
            "nodes_df": pd.DataFrame(),
            "edges_df": pd.DataFrame(),
            "graph_metrics": {
                "team_name": target_team,
                "nodes_count": 0,
                "edges_count": 0,
                "total_completed_passes_in_network": 0,
            },
        }


if __name__ == "__main__":
    import json
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.preprocessing.event_cleaner import EventPreprocessor

    print("=" * 78)
    print("TACTICAL INTELLIGENCE LAB - TEORIA DOS GRAFOS E REDES DE PASSES (DIA 4)")
    print("=" * 78)

    loader = StatsBombDataLoader()
    match_id = 3869685  # Final Copa 2022: Argentina vs França

    raw_df = loader.ingest_match_events(match_id)
    enriched_df = EventPreprocessor.process_match_events(raw_df)

    for team in enriched_df["team_name"].unique():
        net_result = PassingNetworkAnalyzer.build_pass_network(
            enriched_df, target_team=team, until_first_sub=True, min_pass_count=2
        )
        gm = net_result["graph_metrics"]
        nodes_df = net_result["nodes_df"]

        print(f"\n======================================================================")
        print(f"ANÁLISE TOPOLÓGICA DA REDE DE PASSES: {team.upper()}")
        print(f"======================================================================")
        print(f"  * Janela Estrutural Analisada: 0 min até {gm['analyzed_until_minute']} min (1ª Substituição)")
        print(f"  * Estrutura Posicional Real Detectada: {gm['inferred_positional_structure']}")
        print(f"  * Densidade do Grafo: {gm['network_density']} | Reciprocidade (Tabelas): {gm['network_reciprocity']} | Clustering: {gm['avg_clustering_coefficient']}")
        print(f"  * Pivô / Ponte Crítica (Maior Betweenness Centrality): {gm['primary_bridge_player_betweenness']} ({gm['primary_bridge_score']})")
        print(f"  * Organizador Gravitacional (Maior PageRank): {gm['primary_gravity_playmaker_pagerank']} ({gm['primary_playmaker_pagerank_score']})")
        print(f"  * Concentração Máxima de Volume: {gm['highest_volume_distributor']} ({gm['max_player_pass_share_pct']}% dos passes da equipe)")
        print(f"  * Balanço Horizontal: Centroide Y = {gm['team_weighted_centroid_y']} ({gm['lateral_asymmetry_diagnosis']})")
        print(f"\n  [Top 3 Conexões / Vetores de Passe]:")
        for comb in gm["top_5_pass_combinations"][:3]:
            print(f"    -> {comb['pair']}: {comb['passes']} passes ({comb['progressive_passes']} progressivos)")

        print(f"\n  [Top 4 Jogadores por Centralidade Estrutural]:")
        print(
            nodes_df[
                [
                    "player_name",
                    "avg_x",
                    "avg_y",
                    "passes_made",
                    "betweenness_centrality",
                    "pagerank_centrality",
                ]
            ]
            .head(4)
            .to_string(index=False)
        )

        safe_team = team.lower().replace(" ", "_")
        nodes_df.to_csv(f"data/processed/network_nodes_{match_id}_{safe_team}.csv", index=False)
        net_result["edges_df"].to_csv(
            f"data/processed/network_edges_{match_id}_{safe_team}.csv", index=False
        )
        with open(
            f"data/processed/network_metrics_{match_id}_{safe_team}.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(gm, f, ensure_ascii=False, indent=2)