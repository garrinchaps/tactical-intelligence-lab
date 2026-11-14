"""
Contexto da partida carregada, cálculos pesados com cache e registro de proveniência.

`ctx.prov(chave, rótulo, valor, método)` cria o ProvenanceRecord de qualquer métrica exibida:
* valor lido direto da fonte (placar, estatística de boxscore) → tier da fonte (OFFICIAL/DERIVED);
* valor calculado pelo laboratório a partir de eventos reais      → DERIVED;
* partida simulada                                               → SIMULATED + gerador + IC 95%.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from src.canonical.provenance import ProvenanceRecord, ProvenanceRegistry
from src.data_hub.registry import provenance_base
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


@st.cache_data(show_spinner=False, max_entries=8)
def simulation_uncertainty(match_id: int, home: str, away: str, B: int = 100) -> Dict[str, Any]:
    from src.connectors.empirical_fallback import SimulationUncertainty

    return SimulationUncertainty.compute(match_id, home, away, B=B)


SIM_KEYS = {"ppda": "ppda", "field_tilt_pct": "field_tilt_pct", "total_xg": "total_xg",
            "total_shots": "total_shots", "overall_pass_completion_pct": "overall_pass_completion_pct"}


@dataclass
class MatchContext:
    bundle: MatchBundle
    target_team: str
    opponent: str
    df: Optional[pd.DataFrame] = None
    chains: Optional[pd.DataFrame] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    opp_summary: Dict[str, Any] = field(default_factory=dict)
    registry: ProvenanceRegistry = field(default_factory=ProvenanceRegistry)
    sim_ci: Optional[Dict[str, Any]] = None

    # ---------------------------------------------------------------- atalhos
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
    def base(self) -> Dict[str, str]:
        return provenance_base(self.bundle.source)

    @property
    def raw_tier(self) -> str:
        return "SIMULATED" if self.is_sim else self.base["raw_tier"]

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

    # ------------------------------------------------------------ proveniência
    def prov(self, key: str, label: str, value: Any, method: str, raw: bool = False,
             team: Optional[str] = None, sim_key: Optional[str] = None, inputs: Optional[List[str]] = None,
             tier: Optional[str] = None) -> ProvenanceRecord:
        """
        raw=True  → valor lido direto da fonte (tier da fonte);
        raw=False → calculado pelo laboratório (DERIVED).
        Em partida simulada o tier é SIMULATED e, se `sim_key` for dado, o IC 95% vem da re-simulação.
        """
        b = self.base
        if self.is_sim:
            t, gen, lo, hi = "SIMULATED", b["connector"], None, None
            if sim_key and self.sim_ci and team in self.sim_ci.get("teams", {}):
                ci = self.sim_ci["teams"][team].get(sim_key)
                if ci:
                    lo, hi = ci["ci_low"], ci["ci_high"]
                    gen = self.sim_ci.get("generator", gen)
            rec = ProvenanceRecord(key=key, label=label, value=value, source=b["source"], connector=b["connector"],
                                   license=b["license"], confidence_tier=t, method=method, match_id=str(self.match_id),
                                   generator=gen, ci_low=lo, ci_high=hi, inputs=inputs or [])
        else:
            t = tier or (b["raw_tier"] if raw else "DERIVED")
            src = b["source"] if raw else f"{b['source']} → cálculo do laboratório"
            rec = ProvenanceRecord(key=key, label=label, value=value, source=src, connector=b["connector"],
                                   license=b["license"], confidence_tier=t, method=method, match_id=str(self.match_id),
                                   inputs=inputs or [])
        return self.registry.register(rec)


def teams_of(bundle: MatchBundle, df: Optional[pd.DataFrame]) -> List[str]:
    if df is not None and not df.empty:
        return df["team_name"].dropna().unique().tolist()
    m = bundle.meta or {}
    return [t for t in (m.get("home_team_name"), m.get("away_team_name")) if t]


def build_context(bundle: MatchBundle, target_team: Optional[str] = None,
                  upload_df: Optional[pd.DataFrame] = None, with_sim_ci: bool = True) -> MatchContext:
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
    if ctx.is_sim and with_sim_ci and len(teams) == 2:
        try:
            m = bundle.meta or {}
            home = m.get("home_team_name") or teams[0]
            away = m.get("away_team_name") or teams[1]
            if bundle.match_id < 900_000:  # catálogo do gerador por perfis
                ctx.sim_ci = simulation_uncertainty(bundle.match_id, home, away)
        except Exception:
            ctx.sim_ci = None
    return ctx
