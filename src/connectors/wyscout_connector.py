"""WyscoutConnector — eventos do Wyscout Public Dataset no schema canônico."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from src.canonical.schema import to_canonical_events, validate
from src.connectors.base import Connector, ConnectorUnavailable
from src.data_hub.registry import SOURCES


class WyscoutConnector(Connector):
    name = "WyscoutConnector"
    source = SOURCES["wyscout"].label
    license = SOURCES["wyscout"].license_note
    family = "events"
    default_tier = "OFFICIAL"

    def __init__(self, db=None):
        from src.data_hub.db import DataHubDB
        from src.data_hub.sources.wyscout import WyscoutProvider

        self.db = db or DataHubDB()
        self.provider = WyscoutProvider(self.db)

    def internal_events(self, match_id: int) -> pd.DataFrame:
        mid = int(match_id)
        if self.db.has_events(mid):
            return self.db.load_events(mid)
        try:
            return self.provider.load_events(mid)
        except Exception as exc:
            raise ConnectorUnavailable(f"Partida Wyscout {mid} indisponível: {exc}")

    @classmethod
    def canonical_from_internal(cls, df: pd.DataFrame, home_team: Optional[str] = None) -> pd.DataFrame:
        can = to_canonical_events(df, cls.source, cls.name, cls.license, cls.default_tier, home_team=home_team)
        validate(can)
        return can
