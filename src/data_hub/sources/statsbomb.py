"""
StatsBomb Open Data — catálogo COMPLETO com atualização incremental.

* `sync_catalog()` lê competitions.json e, para cada competição/temporada cujo campo
  `match_updated` mudou desde a última sincronização, baixa a lista de partidas.
  Novas temporadas publicadas pela StatsBomb entram sozinhas no catálogo.
* `load_events()` baixa os eventos de uma partida sob demanda (cache permanente) e
  usa o mesmo parser do StatsBombDataLoader.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_hub.http import PoliteHttpClient
from src.data_hub.registry import DataLevel

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CATALOG_MAX_AGE_S = 6 * 3600


class StatsBombProvider:
    source = "statsbomb"

    def __init__(self, db: DataHubDB, client: Optional[PoliteHttpClient] = None):
        self.db = db
        self.client = client or PoliteHttpClient("statsbomb", db=db, min_interval_s=0.2)

    @staticmethod
    def parse_matches(raw: List[Dict[str, Any]], comp: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for m in raw:
            home, away = m.get("home_team") or {}, m.get("away_team") or {}
            competition = m.get("competition") or {}
            season = m.get("season") or {}
            stage = m.get("competition_stage") or {}
            out.append({
                "match_id": int(m["match_id"]),
                "source_match_id": str(m["match_id"]),
                "competition_id": int(competition.get("competition_id", comp.get("competition_id", 0))),
                "competition_name": competition.get("competition_name", comp.get("competition_name", "")),
                "season_id": int(season.get("season_id", comp.get("season_id", 0))),
                "season_name": season.get("season_name", comp.get("season_name", "")),
                "country_name": competition.get("country_name", comp.get("country_name", "")),
                "match_date": m.get("match_date", ""),
                "home_team_id": int(home.get("home_team_id", 0) or 0),
                "home_team_name": home.get("home_team_name", ""),
                "away_team_id": int(away.get("away_team_id", 0) or 0),
                "away_team_name": away.get("away_team_name", ""),
                "home_score": m.get("home_score"),
                "away_score": m.get("away_score"),
                "stadium_name": (m.get("stadium") or {}).get("name", ""),
                "referee_name": (m.get("referee") or {}).get("name", ""),
                "has_360_data": 1 if m.get("match_status_360") == "available" else 0,
                "round_name": stage.get("name", "") or (f"Rodada {m['match_week']}" if m.get("match_week") else ""),
                "data_source": "statsbomb",
                "data_level": DataLevel.EVENTS,
                "extra": {"gender": comp.get("competition_gender", ""),
                          "kick_off": m.get("kick_off", "")},
            })
        return out

    def sync_catalog(self, include_women: bool = True, force: bool = False) -> Dict[str, int]:
        comps = self.client.get_json(f"{BASE}/competitions.json", max_age_s=0 if force else CATALOG_MAX_AGE_S)
        totals = {"added": 0, "updated": 0, "seasons_checked": 0, "seasons_refreshed": 0}
        for comp in comps:
            if not include_women and comp.get("competition_gender") == "female":
                continue
            totals["seasons_checked"] += 1
            key = f"{comp['competition_id']}_{comp['season_id']}"
            stamp = str(comp.get("match_updated") or comp.get("match_available") or "")
            if not force and self.db.get_state(self.source, key) == stamp:
                continue
            try:
                raw = self.client.get_json(
                    f"{BASE}/matches/{comp['competition_id']}/{comp['season_id']}.json",
                    max_age_s=0,  # temporada mudou: força download novo
                )
            except Exception:
                continue
            res = self.db.upsert_matches(self.parse_matches(raw, comp))
            totals["added"] += res["added"]
            totals["updated"] += res["updated"]
            totals["seasons_refreshed"] += 1
            self.db.set_state(self.source, key, stamp)
        return totals

    def load_events(self, match_id: int) -> pd.DataFrame:
        from src.ingestion.statsbomb_loader import StatsBombDataLoader

        raw = self.client.get_json(f"{BASE}/events/{int(match_id)}.json", max_age_s=None)
        df = StatsBombDataLoader._parse_raw_events(None, raw, int(match_id))  # parser não usa estado
        if not df.empty:
            if self.db.get_match(match_id) is None:
                teams = df["team_name"].dropna().unique().tolist()
                self.db.upsert_matches([{
                    "match_id": int(match_id), "data_source": "statsbomb", "data_level": DataLevel.EVENTS,
                    "competition_name": "StatsBomb Open Data",
                    "home_team_name": teams[0] if teams else "", "away_team_name": teams[1] if len(teams) > 1 else "",
                }])
            self.db.save_events(match_id, df)
        return df
