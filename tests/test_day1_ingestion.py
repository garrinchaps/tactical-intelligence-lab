"""
Testes Automatizados do Dia 1: Validação do Schema SQLite e Pipeline de Ingestão.
"""

from pathlib import Path
import pandas as pd
import pytest
from src.ingestion.statsbomb_loader import StatsBombDataLoader


def test_sqlite_initialization_and_custom_ingestion(tmp_path: Path):
    """
    Testa se o banco SQLite é criado corretamente e se um conjunto de eventos
    táticos é persistido e recuperado sem perda de precisão espacial.
    """
    test_db = tmp_path / "test_tactical.db"
    loader = StatsBombDataLoader(
        db_path=str(test_db),
        schema_path="database/schema.sql",
        raw_dir=str(tmp_path / "raw"),
    )

    assert test_db.exists(), "O arquivo do banco SQLite deveria ter sido criado."

    # Cria amostra sintética controlada para validar integridade das colunas
    sample_csv = tmp_path / "sample_match.csv"
    df_sample = pd.DataFrame(
        [
            {
                "event_id": "ev_1",
                "team_name": "Equipe A",
                "player_name": "Volante 5",
                "type_name": "Pass",
                "minute": 12,
                "second": 30,
                "x": 42.5,
                "y": 40.0,
                "end_x": 68.0,
                "end_y": 22.5,
                "under_pressure": 1,
            },
            {
                "event_id": "ev_2",
                "team_name": "Equipe A",
                "player_name": "Meia 10",
                "type_name": "Shot",
                "minute": 12,
                "second": 35,
                "x": 104.2,
                "y": 38.0,
                "end_x": 120.0,
                "end_y": 39.5,
                "under_pressure": 0,
            },
        ]
    )
    df_sample.to_csv(sample_csv, index=False)

    # Ingestão e leitura a partir do SQLite
    loader.ingest_custom_csv_or_json(str(sample_csv), match_id=1001)
    loaded_df = loader.load_events_from_db(match_id=1001)

    assert len(loaded_df) == 2
    assert set(loaded_df["team_name"].unique()) == {"Equipe A"}
    assert loaded_df.loc[0, "x"] == pytest.approx(42.5)
    assert loaded_df.loc[0, "end_x"] == pytest.approx(68.0)
    assert loaded_df.loc[1, "type_name"] == "Shot"