"""
Contexto da partida carregada e cálculos pesados com cache.

Tudo que é caro (processar eventos, sumários táticos, rede de passes, clusters) é
calculado uma vez por (partida, equipe) e reaproveitado entre as seções.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.data_hub.service import MatchBundle, MatchDataService
from src.metrics.tactical_metrics import TacticalMetricsEngine
from src.metrics.xt_model import ExpectedThreatModel
from src.preprocessing.event_cleaner import EventPreprocessor


@st.cache_resource(show_spinner=False)
def get_service() -> MatchDataService:
    return MatchDataService()


@st.cache_data(show_spinner=False, max_entries=12)
def load_bundle(match_id: int) -> MatchBundle:
    return get_service().load(int(match_id))


@st.cache_data(show_spinner=False, max_entries=12)
def processed_events(match_id: int, _raw: pd.DataFrame):
    df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(_raw))
    return df, EventPreprocessor.build_possession_chains(df)


@st.cache_data(show_spinner=False, max_entries=24)
def team_summary(match_id: int, team: str, _df: pd.DataFrame, _chains: pd.DataFrame) -> Dict[str, Any]:
    return TacticalMetricsEngine.generate_full_match_tactical_summary(_df, _chains, team)


@dataclass
class MatchContext:
    bundle: MatchBundle
    target_team: str
    opponent: str
    df: Optional[pd.DataFrame] = None
    chains: Optional[pd.DataFrame] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    opp_summary: Dict[str, Any] = field(default_factory=dict)

    @property
    def match_id(self) -> int:
        return self.bundle.match_id

    @property
    def has_events(self) -> bool:
        return self.df is not None and not self.df.empty

    @property
    def is_sim(self) -> bool:
        return self.bundle.is_simulated

    @property
    def players(self) -> List[str]:
        if self.has_events:
            return sorted(self.df["player_name"].dropna().astype(str).unique().tolist())
        lu = self.bundle.boxscore.get("lineups") if self.bundle.boxscore else None
        return sorted(lu["player_name"].tolist()) if lu is not None and not lu.empty else []

    def goals(self, team: str) -> int:
        if not self.has_events:
            return 0
        d = self.df
        shots = ((d["team_name"] == team) & (d["type_name"] == "Shot") &
                 (d.get("shot_outcome_name", pd.Series("")) == "Goal") & (d["period"] <= 4)).sum()
        own = ((d["team_name"] != team) & (d["type_name"] == "Own Goal Against") & (d["period"] <= 4)).sum()
        return int(shots + own)


def teams_of(bundle: MatchBundle, df: Optional[pd.DataFrame]) -> List[str]:
    if df is not None and not df.empty:
        return df["team_name"].dropna().unique().tolist()
    m = bundle.meta or {}
    return [t for t in (m.get("home_team_name"), m.get("away_team_name")) if t]


def build_context(bundle: MatchBundle, target_team: Optional[str] = None,
                  upload_df: Optional[pd.DataFrame] = None) -> MatchContext:
    df = chains = None
    raw = upload_df if upload_df is not None else bundle.events
    if raw is not None and not raw.empty:
        df, chains = processed_events(bundle.match_id, raw)
    teams = teams_of(bundle, df)
    team = target_team if target_team in teams else (teams[0] if teams else "Equipe")
    opp = next((t for t in teams if t != team), "Adversário")
    ctx = MatchContext(bundle=bundle, target_team=team, opponent=opp, df=df, chains=chains)
    if ctx.has_events:
        ctx.summary = team_summary(bundle.match_id, team, df, chains)
        ctx.opp_summary = team_summary(bundle.match_id, opp, df, chains)
    return ctx
