"""
APIConnector (Módulo 3.3) — opcional e desativado por padrão.

Entrada: chave do usuário (no .env) + identificador da partida na API.
Saída: estatísticas da partida no schema canônico de AGREGADOS.
Sem chave → ConnectorUnavailable com mensagem clara; a aplicação segue funcionando.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from src.canonical.schema import make_aggregate_frame
from src.connectors.base import Connector, ConnectorUnavailable
from src.data_hub.registry import SOURCES


class APIConnector(Connector):
    name = "APIConnector"
    source = SOURCES["api_football"].label
    license = SOURCES["api_football"].license_note
    family = "aggregates"
    default_tier = "OFFICIAL"

    def __init__(self, api_key: Optional[str] = None, db=None):
        from src.data_hub.db import DataHubDB
        from src.data_hub.sources.api_football import ApiFootballProvider

        self.db = db or DataHubDB()
        self.provider = ApiFootballProvider(self.db, api_key=api_key)

    @property
    def enabled(self) -> bool:
        return self.provider.enabled

    def fetch_match(self, fixture_id: int) -> pd.DataFrame:
        if not self.enabled:
            raise ConnectorUnavailable(
                "APIConnector desativado: configure API_FOOTBALL_KEY no arquivo .env para usar esta fonte. "
                "O restante da aplicação continua funcionando com as fontes locais.")
        try:
            record, box = self.provider.fetch_fixture_full(int(fixture_id))
        except Exception as exc:
            raise ConnectorUnavailable(f"APIConnector não conseguiu obter a partida {fixture_id}: {exc}")
        return self.boxscore_to_aggregates(record, box)

    @classmethod
    def boxscore_to_aggregates(cls, record: dict, box: dict) -> pd.DataFrame:
        rows = [{"match_id": record["match_id"], "team_id": s["team_name"], "entity": s["team_name"],
                 "metric": s["stat_key"], "value": s["value"]} for s in box.get("team_stats", [])]
        return make_aggregate_frame(rows, cls.source, cls.name, cls.license, cls.default_tier)
