"""
football-data.org — placares oficiais da temporada atual (token gratuito).

Plano grátis: 12 competições (inclui Brasileirão Série A, Premier League, La Liga,
Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga, Championship, Champions
League, Euro e Copa do Mundo), 10 chamadas por minuto, placares com atraso.
Nível de dado: RESULT (só placar e informações da partida). Token em .env: FOOTBALL_DATA_TOKEN=...
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from src.data_hub.db import DataHubDB
from src.data_hub.http import PoliteHttpClient, SourceUnavailable
from src.data_hub.registry import DataLevel, to_internal_id

BASE = "https://api.football-data.org/v4"
FREE_COMPETITIONS = {
    "BSA": "Campeonato Brasileiro Série A", "PL": "Premier League", "PD": "La Liga", "SA": "Serie A",
    "BL1": "Bundesliga", "FL1": "Ligue 1", "DED": "Eredivisie", "PPL": "Primeira Liga",
    "ELC": "Championship", "CL": "UEFA Champions League", "EC": "UEFA Euro", "WC": "FIFA World Cup",
}


class FootballDataProvider:
    source = "football_data"

    def __init__(self, db: DataHubDB, token: Optional[str] = None):
        self.db = db
        self.token = (token or os.getenv("FOOTBALL_DATA_TOKEN", "")).strip()
        self.client = PoliteHttpClient("football_data", db=db, min_interval_s=6.5,
                                       default_headers={"X-Auth-Token": self.token})

    @property
    def enabled(self) -> bool:
        return bool(self.token) and "coloque" not in self.token.lower()

    @staticmethod
    def parse_match(m: Dict[str, Any], code: str = "") -> Dict[str, Any]:
        ft = ((m.get("score") or {}).get("fullTime") or {})
        comp = m.get("competition") or {}
        season = m.get("season") or {}
        refs = m.get("referees") or []
        return {
            "match_id": to_internal_id("football_data", int(m["id"])),
            "source_match_id": str(m["id"]),
            "competition_id": int(comp.get("id") or 0),
            "competition_name": comp.get("name") or FREE_COMPETITIONS.get(code, code),
            "season_id": int((season.get("startDate") or "0")[:4] or 0),
            "season_name": (season.get("startDate") or "")[:4],
            "country_name": ((m.get("area") or {}).get("name") or ""),
            "round_name": f"Rodada {m['matchday']}" if m.get("matchday") else (m.get("stage") or ""),
            "match_date": (m.get("utcDate") or "")[:10],
            "home_team_name": (m.get("homeTeam") or {}).get("name", ""),
            "away_team_name": (m.get("awayTeam") or {}).get("name", ""),
            "home_score": ft.get("home"),
            "away_score": ft.get("away"),
            "referee_name": refs[0].get("name", "") if refs else "",
            "status": m.get("status", ""),
            "data_source": "football_data",
            "data_level": DataLevel.RESULT,
        }

    def matches(self, code: str, d_from: date, d_to: date) -> List[Dict[str, Any]]:
        if not self.enabled:
            raise SourceUnavailable("FOOTBALL_DATA_TOKEN não configurado no .env.")
        recent = (date.today() - d_to).days < 3
        data = self.client.get_json(
            f"{BASE}/competitions/{code}/matches",
            params={"dateFrom": d_from.isoformat(), "dateTo": d_to.isoformat()},
            max_age_s=3600 if recent else None,
        )
        return [self.parse_match(m, code) for m in data.get("matches", []) if m.get("status") == "FINISHED"]

    def sync_recent(self, days_back: int = 7, codes: Optional[List[str]] = None) -> Dict[str, int]:
        totals = {"added": 0, "updated": 0, "errors": 0}
        today = date.today()
        for code in codes or list(FREE_COMPETITIONS):
            try:
                recs = self.matches(code, today - timedelta(days=days_back), today)
            except Exception:
                totals["errors"] += 1
                continue
            r = self.db.upsert_matches(recs)
            totals["added"] += r["added"]
            totals["updated"] += r["updated"]
        return totals
