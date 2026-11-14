"""
StatsBombConnector (Módulo 3.1) — fonte primária oficial.

Lê eventos do SQLite local; se não houver, baixa do StatsBomb Open Data; se a rede falhar,
usa o cache de demonstração versionado em data/demo/ (garante a demo 100% offline das
partidas incluídas). Entrega o DataFrame interno (para o pipeline) e o canônico.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Optional

import pandas as pd

from src.canonical.schema import to_canonical_events, validate
from src.connectors.base import Connector, ConnectorUnavailable
from src.data_hub.registry import SOURCES

DEMO_DIR = Path("data/demo")


def load_demo_events(match_id: int) -> Optional[list]:
    path = DEMO_DIR / f"statsbomb_events_{int(match_id)}.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


class StatsBombConnector(Connector):
    name = "StatsBombConnector"
    source = SOURCES["statsbomb"].label
    license = SOURCES["statsbomb"].license_note
    family = "events"
    default_tier = "OFFICIAL"

    def __init__(self, db=None):
        from src.data_hub.db import DataHubDB
        from src.data_hub.sources.statsbomb import StatsBombProvider

        self.db = db or DataHubDB()
        self.provider = StatsBombProvider(self.db)

    def internal_events(self, match_id: int) -> pd.DataFrame:
        mid = int(match_id)
        if self.db.has_events(mid):
            return self.db.load_events(mid)
        try:
            return self.provider.load_events(mid)
        except Exception as exc:
            raw = load_demo_events(mid)
            if raw is None:
                raise ConnectorUnavailable(
                    f"Partida {mid} indisponível: sem cache local, sem cache de demonstração e sem rede ({exc}).")
            from src.ingestion.statsbomb_loader import StatsBombDataLoader

            df = StatsBombDataLoader._parse_raw_events(None, raw, mid)
            if self.db.get_match(mid) is None:
                teams = df["team_name"].dropna().unique().tolist()
                self.db.upsert_matches([{"match_id": mid, "data_source": "statsbomb", "data_level": "EVENTS",
                                         "competition_name": "StatsBomb Open Data (demo)",
                                         "home_team_name": teams[0], "away_team_name": teams[1]}])
            self.db.save_events(mid, df)
            return df

    def canonical_events(self, match_id: int, home_team: Optional[str] = None) -> pd.DataFrame:
        df = self.internal_events(match_id)
        meta = self.db.get_match(int(match_id)) or {}
        can = to_canonical_events(df, self.source, self.name, self.license, self.default_tier,
                                  home_team=home_team or meta.get("home_team_name"))
        validate(can)
        return can
