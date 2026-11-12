"""
Testes Automatizados do Dia 11: Validação de Renderização Gráfica (mplsoccer e Plotly).
"""

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
from src.preprocessing.event_cleaner import EventPreprocessor
from src.networks.pass_network import PassingNetworkAnalyzer
from src.metrics.xt_model import ExpectedThreatModel
from src.machine_learning.clustering import SpatialTacticalClustering
from src.metrics.tactical_metrics import TacticalMetricsEngine
from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.visualization.pitch_plots import TacticalVisualizer


def test_pitch_plots_and_plotly_generation(tmp_path: Path):
    """
    Verifica se os mapas do campo (Rede de Passes, Progressão xT e Clusters)
    são gerados e exportados como arquivos PNG válidos e se os gráficos Plotly
    retornam estruturas de dados consistentes.
    """
    rows = []
    for i in range(18):
        rows.append(
            {
                "event_id": f"v_{i}",
                "match_id": 1111,
                "period": 1,
                "index_num": i + 1,
                "minute": 5 + i,
                "second": 0,
                "possession": 1 + (i // 4),
                "possession_team_name": "Time Visual",
                "team_name": "Time Visual" if i < 15 else "Adversario",
                "player_name": f"Atleta {i % 4}",
                "pass_recipient_name": f"Atleta {(i + 1) % 4}",
                "position_name": "Midfield",
                "type_name": "Pass",
                "pass_outcome_name": "Incomplete" if i % 4 == 0 else None,
                "x": 30.0 + i * 3.5,
                "y": 20.0 + (i % 5) * 8.0,
                "end_x": 45.0 + i * 3.5,
                "end_y": 25.0 + (i % 5) * 8.0,
                "under_pressure": 1 if i % 3 == 0 else 0,
            }
        )

    df_enriched = EventPreprocessor.process_match_events(pd.DataFrame(rows))
    df_xt = ExpectedThreatModel.enrich_events_with_xt(df_enriched)
    df_chains = EventPreprocessor.build_possession_chains(df_xt)

    net_res = PassingNetworkAnalyzer.build_pass_network(
        df_xt, target_team="Time Visual", until_first_sub=False, min_pass_count=1
    )
    km_res = SpatialTacticalClustering.analyze_turnover_clusters(df_xt, "Time Visual")
    db_res = SpatialTacticalClustering.analyze_recovery_density_dbscan(df_xt, "Time Visual")

    p1 = tmp_path / "net.png"
    p2 = tmp_path / "prog.png"
    p3 = tmp_path / "clust.png"

    fig1 = TacticalVisualizer.plot_passing_network(net_res, save_path=str(p1))
    fig2 = TacticalVisualizer.plot_progression_and_xt_map(
        df_xt, "Time Visual", save_path=str(p2)
    )
    fig3 = TacticalVisualizer.plot_spatial_clusters_and_press_traps(
        df_xt,
        {"kmeans_turnovers": km_res, "dbscan_recoveries": db_res},
        "Time Visual",
        save_path=str(p3),
    )

    plt.close(fig1)
    plt.close(fig2)
    plt.close(fig3)

    assert p1.exists() and p1.stat().st_size > 1000
    assert p2.exists() and p2.stat().st_size > 1000
    assert p3.exists() and p3.stat().st_size > 1000

    # Testa gráficos interativos Plotly
    def_org = TacticalMetricsEngine.compute_defensive_organization(
        df_xt, df_chains, "Time Visual"
    )
    fig_bar = TacticalVisualizer.create_corridor_vulnerability_plotly(
        def_org, "Time Visual"
    )
    assert len(fig_bar.data) == 2

    players_df = PlayerTacticalEvaluator.evaluate_team_players(df_xt, "Time Visual")
    fig_radar = TacticalVisualizer.create_player_comparison_radar_plotly(
        players_df, "Atleta 0", "Atleta 1"
    )
    assert len(fig_radar.data) == 2