"""
Testes Automatizados do Dia 4: Validação de Teoria dos Grafos, Centralidade de
Intermediação (Betweenness Centrality) e Detecção do Pivô da Saída de Bola.
"""

import pandas as pd
import pytest
from src.preprocessing.event_cleaner import EventPreprocessor
from src.networks.pass_network import PassingNetworkAnalyzer


def test_pass_network_identifies_central_pivot_by_betweenness():
    """
    Constrói uma rede onde 'Volante Pivô' é a ponte obrigatória entre a linha
    defensiva ('Zagueiro Dir', 'Zagueiro Esq') e a linha de criação ('Meia 10', 'Ponta').
    Verifica se o grafo atribui a maior Betweenness Centrality exatamente ao 'Volante Pivô'.
    """
    events = []
    idx = 1

    def add_pass(passer: str, recipient: str, x: float, y: float, ex: float, ey: float, count: int):
        nonlocal idx
        for _ in range(count):
            events.append(
                {
                    "event_id": f"net_{idx}",
                    "match_id": 404,
                    "period": 1,
                    "index_num": idx,
                    "minute": 10,
                    "second": idx % 50,
                    "possession": 1,
                    "possession_team_name": "Equipe Tática",
                    "team_name": "Equipe Tática",
                    "player_name": passer,
                    "pass_recipient_name": recipient,
                    "position_name": "Midfield",
                    "type_name": "Pass",
                    "pass_outcome_name": None,
                    "x": x,
                    "y": y,
                    "end_x": ex,
                    "end_y": ey,
                }
            )
            idx += 1

    # Zagueiros sempre passam para o Volante Pivô
    add_pass("Zagueiro Esq", "Volante Pivô", 30.0, 25.0, 50.0, 40.0, count=6)
    add_pass("Zagueiro Dir", "Volante Pivô", 30.0, 55.0, 50.0, 40.0, count=6)
    # Volante Pivô distribui para o Meia 10 e para o Ponta
    add_pass("Volante Pivô", "Meia 10", 50.0, 40.0, 75.0, 40.0, count=6)
    add_pass("Volante Pivô", "Ponta Esq", 50.0, 40.0, 82.0, 15.0, count=5)
    # Retorno ocasional do Meia 10 para o Volante Pivô
    add_pass("Meia 10", "Volante Pivô", 75.0, 40.0, 52.0, 40.0, count=3)

    df_raw = pd.DataFrame(events)
    df_enriched = EventPreprocessor.process_match_events(df_raw)

    net = PassingNetworkAnalyzer.build_pass_network(
        df_enriched, target_team="Equipe Tática", until_first_sub=False, min_pass_count=1
    )

    gm = net["graph_metrics"]
    nodes_df = net["nodes_df"]

    assert gm["nodes_count"] == 5
    assert gm["primary_bridge_player_betweenness"] == "Volante Pivô"
    assert gm["highest_volume_distributor"] == "Volante Pivô"
    assert nodes_df.iloc[0]["player_name"] == "Volante Pivô"
    # Em um DiGraph de 5 nós, 5 caminhos intermediados em (5-1)*(5-2)=12 pares possíveis = 5/12 (0.4167)
    assert nodes_df.iloc[0]["betweenness_centrality"] == pytest.approx(5.0 / 12.0, abs=1e-4)
    assert nodes_df.iloc[1]["betweenness_centrality"] == pytest.approx(0.0)