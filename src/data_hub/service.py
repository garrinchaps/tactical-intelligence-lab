"""
Serviço de partidas: dado um match_id interno, entrega tudo o que existe sobre a
partida no nível de dado correto (eventos, boxscore, só placar ou simulação).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_hub.registry import (
    BADGES, LEVEL_DESCRIPTIONS, SOURCES, DataLevel, badge_for, source_from_internal_id,
)
from src.data_hub.search import UniversalMatchFinder
from src.data_hub.sources.api_football import ApiFootballProvider
from src.data_hub.sources.espn import EspnProvider
from src.data_hub.sources.football_data import FootballDataProvider
from src.data_hub.sources.statsbomb import StatsBombProvider
from src.data_hub.sources.wyscout import WyscoutProvider


@dataclass
class MatchBundle:
    match_id: int
    meta: Dict[str, Any]
    level: str
    source: str
    events: Optional[pd.DataFrame] = None
    boxscore: Dict[str, Any] = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def badge(self) -> str:
        return badge_for(self.level)

    @property
    def level_description(self) -> str:
        return LEVEL_DESCRIPTIONS.get(self.level, "")

    @property
    def source_label(self) -> str:
        return SOURCES[self.source].label if self.source in SOURCES else self.source.capitalize()

    @property
    def has_events(self) -> bool:
        return self.events is not None and not self.events.empty

    @property
    def is_simulated(self) -> bool:
        return self.level == DataLevel.SIMULATED


class MatchDataService:
    def __init__(self, db: Optional[DataHubDB] = None):
        self.db = db or DataHubDB()
        self.statsbomb = StatsBombProvider(self.db)
        self.wyscout = WyscoutProvider(self.db)
        self.api_football = ApiFootballProvider(self.db)
        self.football_data = FootballDataProvider(self.db)
        self.espn = EspnProvider(self.db)
        self.finder = UniversalMatchFinder(self.db, providers={
            "api_football": self.api_football, "espn": self.espn, "football_data": self.football_data,
        })

    def providers_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            "statsbomb": {"enabled": True, "note": "sem chave"},
            "wyscout": {"enabled": True, "note": "sem chave"},
            "api_football": {"enabled": self.api_football.enabled,
                             "quota_left": self.api_football.client.quota_left() if self.api_football.enabled else None},
            "football_data": {"enabled": self.football_data.enabled},
            "espn": {"enabled": self.espn.enabled},
        }

    def load(self, match_id: int) -> MatchBundle:
        mid = int(match_id)
        meta = self.db.get_match(mid) or {}
        source = meta.get("data_source") or source_from_internal_id(mid)
        level = meta.get("data_level") or DataLevel.EVENTS

        if source in ("statsbomb", "wyscout"):
            events = self.db.load_events(mid) if self.db.has_events(mid) else None
            if events is None or events.empty:
                provider = self.statsbomb if source == "statsbomb" else self.wyscout
                events = provider.load_events(mid)
            meta = self.db.get_match(mid) or meta
            return MatchBundle(mid, meta, DataLevel.EVENTS, source, events=events)

        if source == "simulated":
            from src.ingestion.statsbomb_loader import StatsBombDataLoader

            loader = StatsBombDataLoader()
            events = loader.ingest_match_events(mid) if mid < 900_000 else loader.generate_tactical_simulation_match(
                home_team=meta.get("home_team_name", "Equipe A"),
                away_team=meta.get("away_team_name", "Equipe B"), match_id=mid)
            return MatchBundle(mid, meta, DataLevel.SIMULATED, "simulated", events=events)

        if source == "upload":
            return MatchBundle(mid, meta, DataLevel.UPLOAD, "upload", events=self.db.load_events(mid))

        notes = []
        if source in ("api_football", "espn") and not self.db.has_boxscore(mid):
            try:
                (self.api_football.ingest_fixture if source == "api_football" else self.espn.ingest_event)(mid)
            except Exception as exc:
                notes.append(f"Não foi possível baixar o boxscore agora: {exc}")
        meta = self.db.get_match(mid) or meta
        box = self.db.load_boxscore(mid)
        has_box = not box["team_stats"].empty or not box["lineups"].empty
        level = DataLevel.BOXSCORE if has_box else DataLevel.RESULT
        if meta and meta.get("data_level") != level and has_box:
            self.db.set_level(mid, level)
        return MatchBundle(mid, meta, level, source, boxscore=box, notes=notes)
