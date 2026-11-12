"""
Módulo de Visualização Científica de Futebol (Camada 5 - Visualização)
Utiliza mplsoccer, Matplotlib e Plotly para renderizar mapas táticos auditáveis:
1. Rede de Passes Direcionada com Centralidade Betweenness e Estrutura Posicional.
2. Mapa de Ações Progressivas, Quebras de Linha (Delta xT), Zona 14 e xG.
3. Mapa Espacial de Clusters de Perdas (K-Means + Exposição) e Recuperações (DBSCAN).
4. Gráficos Interativos Plotly (Comparação Head-to-Head de Atletas e Corredores).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
from mplsoccer import Pitch
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Garante backend seguro sem abrir janelas bloqueantes no Windows/Pytest
matplotlib.use("Agg")


class TacticalVisualizer:
    """
    Motor gráfico para geração de mapas de campo (mplsoccer) e gráficos interativos (Plotly).
    Todas as funções retornam o objeto Figure e opcionalmente salvam em disco.
    """

    BG_DARK = "#0f172a"
    PITCH_COLOR = "#1e293b"
    LINE_COLOR = "#94a3b8"
    TEXT_LIGHT = "#f8fafc"
    ACCENT_CYAN = "#38bdf8"
    ACCENT_GOLD = "#facc15"
    ACCENT_RED = "#f43f5e"
    ACCENT_GREEN = "#22c55e"

    @classmethod
    def plot_passing_network(
        cls,
        network_data: Dict[str, Any],
        save_path: Optional[str] = None,
    ) -> plt.Figure:
        """
        1. Renderiza o Mapa da Rede de Passes da equipe:
        - Nós posicionados em (avg_x, avg_y).
        - Tamanho do nó proporcional ao envolvimento e Betweenness Centrality.
        - Anel dourado destacando o Pivô da Construção (Maior Betweenness).
        - Arestas com espessura e opacidade proporcionais ao volume de passes da dupla.
        """
        nodes_df: pd.DataFrame = network_data.get("nodes_df", pd.DataFrame())
        edges_df: pd.DataFrame = network_data.get("edges_df", pd.DataFrame())
        gm: Dict[str, Any] = network_data.get("graph_metrics", {})
        team_name = gm.get("team_name", "Equipe")

        pitch = Pitch(
            pitch_type="statsbomb",
            pitch_color=cls.PITCH_COLOR,
            line_color=cls.LINE_COLOR,
            linewidth=1.5,
        )
        fig, ax = pitch.draw(figsize=(11, 7.5))
        fig.set_facecolor(cls.BG_DARK)

        if nodes_df.empty:
            ax.text(
                60,
                40,
                f"Sem dados suficientes para rede de passes ({team_name})",
                color=cls.TEXT_LIGHT,
                ha="center",
                va="center",
                fontsize=13,
            )
            return fig

        # Desenha as arestas (conexões de passe)
        if not edges_df.empty:
            max_passes = max(float(edges_df["pass_count"].max()), 1.0)
            for _, edge in edges_df.iterrows():
                w = float(edge["pass_count"])
                lw = 1.2 + (w / max_passes) * 6.5
                alpha = min(0.30 + (w / max_passes) * 0.65, 0.95)
                pitch.lines(
                    edge["source_x"],
                    edge["source_y"],
                    edge["target_x"],
                    edge["target_y"],
                    lw=lw,
                    color=cls.ACCENT_CYAN,
                    alpha=alpha,
                    zorder=2,
                    ax=ax,
                )

        # Desenha os nós (jogadores)
        max_bt = max(float(nodes_df["betweenness_centrality"].max()), 0.01)
        primary_bridge = gm.get("primary_bridge_player_betweenness", "")

        for _, node in nodes_df.iterrows():
            px = float(node["avg_x"])
            py = float(node["avg_y"])
            bt = float(node["betweenness_centrality"])
            node_size = 320 + (bt / max_bt) * 580

            is_pivot = str(node["player_name"]) == str(primary_bridge)
            edge_col = cls.ACCENT_GOLD if is_pivot else cls.TEXT_LIGHT
            face_col = "#e11d48" if is_pivot else "#0284c7"

            pitch.scatter(
                px,
                py,
                s=node_size,
                color=face_col,
                edgecolors=edge_col,
                linewidth=2.8 if is_pivot else 1.5,
                alpha=0.95,
                zorder=4,
                ax=ax,
            )

            # Nome abreviado (último sobrenome) para leitura limpa
            short_name = str(node["player_name"]).split()[-1]
            ax.text(
                px,
                py - 3.0,
                f"{short_name}\n({int(node['passes_made'])}p)",
                color=cls.TEXT_LIGHT,
                fontsize=8.5,
                fontweight="bold",
                ha="center",
                va="bottom",
                zorder=5,
                bbox=dict(
                    boxstyle="round,pad=0.18",
                    facecolor=cls.BG_DARK,
                    edgecolor="none",
                    alpha=0.75,
                ),
            )

        # Linha vertical da média de altura posicional da equipe
        mean_team_x = float(nodes_df["avg_x"].mean())
        ax.axvline(
            mean_team_x,
            color=cls.ACCENT_GOLD,
            linestyle="--",
            linewidth=1.4,
            alpha=0.7,
        )

        title_str = (
            f"REDE DE PASSES E TOPOLOGIA ESTRUTURAL — {team_name.upper()}\n"
            f"Estrutura Real: {gm.get('inferred_positional_structure', 'N/A')} | "
            f"Pivô (Maior Betweenness): {primary_bridge} ({gm.get('primary_bridge_score', 0.0)}) | "
            f"Até min {gm.get('analyzed_until_minute', 90.0)}"
        )
        ax.set_title(
            title_str,
            color=cls.TEXT_LIGHT,
            fontsize=11.5,
            fontweight="bold",
            pad=12,
        )

        ax.text(
            2,
            78.5,
            "Fonte: StatsBomb Open Data | Tactical Intelligence Lab (Direção de Ataque: Esquerda -> Direita)",
            color=cls.LINE_COLOR,
            fontsize=8,
        )

        fig.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=220, facecolor=cls.BG_DARK)

        return fig

    @classmethod
    def plot_progression_and_xt_map(
        cls,
        df_events_xt: pd.DataFrame,
        target_team: str,
        save_path: Optional[str] = None,
    ) -> plt.Figure:
        """
        2. Renderiza o Mapa de Progressão Territorial, Quebras de Linha (xT),
        destaque geométrico da Zona 14 e Finalizações ponderadas por xG.
        """
        team_ev = df_events_xt[df_events_xt["team_name"] == target_team].copy()

        pitch = Pitch(
            pitch_type="statsbomb",
            pitch_color=cls.PITCH_COLOR,
            line_color=cls.LINE_COLOR,
            linewidth=1.5,
        )
        fig, ax = pitch.draw(figsize=(11, 7.5))
        fig.set_facecolor(cls.BG_DARK)

        # Destaca a Zona 14 (80 <= x < 102, 26.67 <= y <= 53.33) no gramado
        z14_rect = Rectangle(
            (80.0, 26.67),
            22.0,
            26.66,
            linewidth=1.8,
            edgecolor=cls.ACCENT_GOLD,
            facecolor=cls.ACCENT_GOLD,
            alpha=0.14,
            linestyle="--",
            zorder=1,
        )
        ax.add_patch(z14_rect)
        ax.text(
            91.0,
            28.5,
            "ZONA 14",
            color=cls.ACCENT_GOLD,
            fontsize=8.5,
            fontweight="bold",
            ha="center",
            alpha=0.85,
        )

        # Filtra passes progressivos e quebras de linha
        prog_passes = team_ev[
            (team_ev["type_name"] == "Pass")
            & (team_ev["is_pass_completed"] == 1)
            & (
                (team_ev["is_progressive_action"] == 1)
                | (team_ev.get("is_line_breaking_pass", 0) == 1)
            )
            & (team_ev["x"].notna())
            & (team_ev["end_x"].notna())
        ]

        for _, row in prog_passes.iterrows():
            is_z14_or_box = (row.get("is_zone_14_entry", 0) == 1) or (
                row.get("is_box_entry", 0) == 1
            )
            arrow_color = cls.ACCENT_GOLD if is_z14_or_box else cls.ACCENT_CYAN
            pitch.arrows(
                row["x"],
                row["y"],
                row["end_x"],
                row["end_y"],
                width=1.8 if is_z14_or_box else 1.2,
                headwidth=4.5,
                headlength=4.5,
                color=arrow_color,
                alpha=0.85 if is_z14_or_box else 0.50,
                zorder=3 if is_z14_or_box else 2,
                ax=ax,
            )

        # Plota finalizações (Shots) com tamanho proporcional ao xG
        shots = team_ev[
            (team_ev["type_name"] == "Shot") & (team_ev["x"].notna())
        ]
        for _, srow in shots.iterrows():
            xg_val = float(srow.get("shot_statsbomb_xg", 0.05) or 0.05)
            is_goal = str(srow.get("shot_outcome_name", "")) == "Goal"
            pitch.scatter(
                srow["x"],
                srow["y"],
                s=120 + xg_val * 900,
                color=cls.ACCENT_GREEN if is_goal else cls.ACCENT_RED,
                edgecolors=cls.TEXT_LIGHT,
                linewidth=1.8,
                marker="*" if is_goal else "o",
                alpha=0.92,
                zorder=5,
                ax=ax,
            )

        n_prog = int(len(prog_passes))
        n_z14 = int(team_ev.get("is_zone_14_entry", pd.Series(0)).sum())
        n_box = int(team_ev.get("is_box_entry", pd.Series(0)).sum())
        total_xt = round(
            float(team_ev[team_ev.get("delta_xt", 0) > 0]["delta_xt"].sum())
            if "delta_xt" in team_ev.columns
            else 0.0,
            3,
        )

        ax.set_title(
            f"VETORES DE PROGRESSÃO, ZONA 14 E EXPECTED THREAT (xT) — {target_team.upper()}\n"
            f"Passes Progressivos: {n_prog} | Entradas Zona 14: {n_z14} | Entradas na Área: {n_box} | +xT Gerado: {total_xt}",
            color=cls.TEXT_LIGHT,
            fontsize=11.0,
            fontweight="bold",
            pad=12,
        )
        ax.text(
            2,
            78.5,
            "Setas Douradas = Infiltração Zona 14 / Grande Área | Setas Azuis = Progressão Territorial | Estrelas Verdes = Gols",
            color=cls.LINE_COLOR,
            fontsize=8,
        )

        fig.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=220, facecolor=cls.BG_DARK)

        return fig

    @classmethod
    def plot_spatial_clusters_and_press_traps(
        cls,
        df_events: pd.DataFrame,
        clustering_bundle: Dict[str, Any],
        target_team: str,
        save_path: Optional[str] = None,
    ) -> plt.Figure:
        """
        3. Renderiza o Mapa de Aprendizado Não Supervisionado:
        - Pontos individuais de perda de posse (Turnovers).
        - Centroides K-Means com círculo de exposição (18 jardas) e taxa de perda por toque (%).
        - Zonas densas de recuperação defensiva detectadas via DBSCAN (Pressing Traps).
        """
        team_ev = df_events[df_events["team_name"] == target_team]
        turnovers = team_ev[
            (team_ev["is_turnover"] == 1) & (team_ev["x"].notna())
        ]

        km_data = clustering_bundle.get("kmeans_turnovers", clustering_bundle)
        db_data = clustering_bundle.get("dbscan_recoveries", {})

        pitch = Pitch(
            pitch_type="statsbomb",
            pitch_color=cls.PITCH_COLOR,
            line_color=cls.LINE_COLOR,
            linewidth=1.5,
        )
        fig, ax = pitch.draw(figsize=(11, 7.5))
        fig.set_facecolor(cls.BG_DARK)

        # Plota cada perda de posse individual
        if not turnovers.empty:
            pitch.scatter(
                turnovers["x"],
                turnovers["y"],
                s=35,
                color=cls.ACCENT_RED,
                alpha=0.45,
                label="Perdas de Posse (Turnovers)",
                zorder=2,
                ax=ax,
            )

        # Desenha os clusters K-Means e seus raios de exposição (18 jardas)
        clusters = km_data.get("clusters", [])
        risk_cluster = km_data.get("highest_risk_exposure_cluster") or {}
        risk_id = risk_cluster.get("cluster_id", -999)

        for c in clusters:
            cx, cy = float(c["centroid_x"]), float(c["centroid_y"])
            is_highest_risk = c["cluster_id"] == risk_id
            ring_color = cls.ACCENT_GOLD if is_highest_risk else cls.ACCENT_RED

            exposure_circle = Circle(
                (cx, cy),
                radius=18.0,
                edgecolor=ring_color,
                facecolor=ring_color,
                alpha=0.16 if is_highest_risk else 0.08,
                linewidth=2.2 if is_highest_risk else 1.2,
                linestyle="--",
                zorder=3,
            )
            ax.add_patch(exposure_circle)

            pitch.scatter(
                cx,
                cy,
                s=260,
                color=ring_color,
                edgecolors=cls.BG_DARK,
                linewidth=2.0,
                zorder=5,
                ax=ax,
            )
            ax.text(
                cx,
                cy,
                f"C{c['cluster_id']}: {c['turnover_rate_per_touch_pct']}%\n({c['turnovers_in_cluster']} err)",
                color=cls.TEXT_LIGHT,
                fontsize=8.5,
                fontweight="bold",
                ha="center",
                va="center",
                zorder=6,
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor=cls.BG_DARK,
                    edgecolor=ring_color,
                    alpha=0.85,
                ),
            )

        # Desenha os Pressing Traps (núcleos DBSCAN de recuperação de bola)
        for trap in db_data.get("pressing_traps", [])[:3]:
            tx, ty = float(trap["centroid_x"]), float(trap["centroid_y"])
            pitch.scatter(
                tx,
                ty,
                s=300,
                color=cls.ACCENT_GREEN,
                edgecolors=cls.TEXT_LIGHT,
                marker="D",
                linewidth=1.8,
                zorder=5,
                ax=ax,
            )
            ax.text(
                tx,
                ty + 4.2,
                f"Trap DBSCAN\n({trap['recoveries_count']} rec)",
                color=cls.ACCENT_GREEN,
                fontsize=8,
                fontweight="bold",
                ha="center",
                zorder=6,
            )

        ax.set_title(
            f"CLUSTERIZAÇÃO ESPACIAL DE PERDAS (K-MEANS) E RECUPERAÇÕES (DBSCAN) — {target_team.upper()}\n"
            f"K Ótimo = {km_data.get('optimal_k', 0)} (Silhouette = {km_data.get('silhouette_score', 0.0)}) | "
            f"Anel Dourado = Maior Taxa de Erro Ajustada por Exposição",
            color=cls.TEXT_LIGHT,
            fontsize=11.0,
            fontweight="bold",
            pad=12,
        )

        fig.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=220, facecolor=cls.BG_DARK)

        return fig

    @classmethod
    def create_corridor_vulnerability_plotly(
        cls, def_org_metrics: Dict[str, Any], target_team: str
    ) -> go.Figure:
        """
        4A. Cria gráfico interativo Plotly comparando a vulnerabilidade defensiva
        nos 5 setores horizontais (ações progressivas cedidas vs. entradas na área).
        """
        breakdown = def_org_metrics.get("corridor_vulnerability_breakdown", {})
        sectors = list(breakdown.keys())
        prog_conceded = [
            breakdown[s]["progressive_actions_conceded"] for s in sectors
        ]
        box_conceded = [breakdown[s]["box_entries_conceded"] for s in sectors]

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                name="Progressões Cedidas ao Adversário",
                x=sectors,
                y=prog_conceded,
                marker_color="#f43f5e",
                text=prog_conceded,
                textposition="auto",
            )
        )
        fig.add_trace(
            go.Bar(
                name="Entradas na Área Cedidas",
                x=sectors,
                y=box_conceded,
                marker_color="#facc15",
                text=box_conceded,
                textposition="auto",
            )
        )

        fig.update_layout(
            title=f"Vulnerabilidade por Corredor Defensivo — {target_team}",
            barmode="group",
            template="plotly_dark",
            xaxis_title="Setor Defensivo da Equipe",
            yaxis_title="Contagem de Eventos Cedidos",
            height=420,
        )
        return fig

    @classmethod
    def create_player_comparison_radar_plotly(
        cls, df_players: pd.DataFrame, player_a: str, player_b: str
    ) -> go.Figure:
        """
        4B. Cria um Gráfico de Radar Interativo (Plotly) comparando dois jogadores
        em 6 dimensões normalizadas (0 a 100% do máximo da equipe na partida).
        """
        categories = [
            "Passes Completos",
            "Retenção sob Pressão (%)",
            "Ações Progressivas",
            "Passes Quebra-Linhas",
            "xT Gerado",
            "Recuperações de Bola",
        ]
        cols = [
            "passes_completed",
            "press_retention_pct",
            "progressive_actions",
            "line_breaking_passes",
            "xt_generated",
            "ball_recoveries",
        ]

        fig = go.Figure()
        if df_players.empty:
            return fig

        max_vals = {
            c: max(float(df_players[c].max()), 1e-4) for c in cols
        }

        for p_name, color_hex in [(player_a, "#38bdf8"), (player_b, "#facc15")]:
            row = df_players[df_players["player_name"] == p_name]
            if row.empty:
                continue
            r = row.iloc[0]
            norm_scores = [
                round((float(r[c]) / max_vals[c]) * 100.0, 1) for c in cols
            ]
            # Fecha o polígono repetindo o primeiro valor
            norm_scores.append(norm_scores[0])
            cat_closed = categories + [categories[0]]

            fig.add_trace(
                go.Scatterpolar(
                    r=norm_scores,
                    theta=cat_closed,
                    fill="toself",
                    name=f"{p_name} ({r['position_name']})",
                    line_color=color_hex,
                )
            )

        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title=f"Comparação Funcional Tática (Percentil Relativo na Partida): {player_a} vs {player_b}",
            template="plotly_dark",
            height=450,
        )
        return fig


if __name__ == "__main__":
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.preprocessing.event_cleaner import EventPreprocessor
    from src.networks.pass_network import PassingNetworkAnalyzer
    from src.metrics.xt_model import ExpectedThreatModel
    from src.machine_learning.clustering import SpatialTacticalClustering

    print("=" * 80)
    print("TACTICAL INTELLIGENCE LAB - VISUALIZAÇÃO CIENTÍFICA MPLSOCCER & PLOTLY (DIA 11)")
    print("=" * 80)

    loader = StatsBombDataLoader()
    match_id = 3869685  # Final Copa 2022: Argentina vs França

    raw_df = loader.ingest_match_events(match_id)
    enriched_df = EventPreprocessor.process_match_events(raw_df)
    xt_df = ExpectedThreatModel.enrich_events_with_xt(enriched_df)

    for team in ["Argentina", "France"]:
        safe_team = team.lower().replace(" ", "_")
        print(f"\n[Renderizando Mapas Táticos de Alta Resolução (220 DPI): {team.upper()}]")

        # 1. Rede de Passes
        net_res = PassingNetworkAnalyzer.build_pass_network(
            xt_df, target_team=team, until_first_sub=True
        )
        f1_path = f"data/processed/figures/pass_network_{match_id}_{safe_team}.png"
        fig1 = TacticalVisualizer.plot_passing_network(net_res, save_path=f1_path)
        plt.close(fig1)
        print(f"  -> [1/3] Mapa da Rede de Passes salvo em: {f1_path}")

        # 2. Progressão, Zona 14 e xT
        f2_path = f"data/processed/figures/progression_xt_{match_id}_{safe_team}.png"
        fig2 = TacticalVisualizer.plot_progression_and_xt_map(
            xt_df, target_team=team, save_path=f2_path
        )
        plt.close(fig2)
        print(f"  -> [2/3] Mapa de Progressão, Zona 14 e xT salvo em: {f2_path}")

        # 3. Clusters K-Means e DBSCAN
        km_res = SpatialTacticalClustering.analyze_turnover_clusters(xt_df, team)
        db_res = SpatialTacticalClustering.analyze_recovery_density_dbscan(xt_df, team)
        f3_path = f"data/processed/figures/clusters_turnovers_{match_id}_{safe_team}.png"
        fig3 = TacticalVisualizer.plot_spatial_clusters_and_press_traps(
            xt_df,
            {"kmeans_turnovers": km_res, "dbscan_recoveries": db_res},
            target_team=team,
            save_path=f3_path,
        )
        plt.close(fig3)
        print(f"  -> [3/3] Mapa de Clusters K-Means e DBSCAN salvo em: {f3_path}")

    print("\n[OK] Dia 11 concluído! Você pode abrir a pasta data/processed/figures/ no VS Code para ver os 6 mapas gerados.")