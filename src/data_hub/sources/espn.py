"""
ESPN — feed JSON público (NÃO oficial, sem documentação, DESATIVADO por padrão).

Cobre jogos atuais de muitas ligas (Brasileirão A/B, Copa do Brasil, Libertadores,
Sul-Americana, ligas europeias...) com placar, estatísticas dos times, escalações e
lances principais. Por ser um endpoint não documentado, pode mudar sem aviso, e o uso
deve respeitar os termos da ESPN: só pessoal/acadêmico, com baixa frequência (1 req/2 s)
e cache. Ativar em .env: ENABLE_ESPN_PUBLIC_FEED=true
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.data_hub.boxscore import ESPN_MAP, stat_row
from src.data_hub.db import DataHubDB
from src.data_hub.http import PoliteHttpClient, SourceUnavailable
from src.data_hub.registry import DataLevel, to_internal_id

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

LEAGUES: Dict[str, str] = {
    "bra.1": "Brasileirão Série A", "bra.2": "Brasileirão Série B", "bra.copa_do_brazil": "Copa do Brasil",
    "conmebol.libertadores": "CONMEBOL Libertadores", "conmebol.sudamericana": "CONMEBOL Sul-Americana",
    "eng.1": "Premier League", "esp.1": "La Liga", "ita.1": "Serie A", "ger.1": "Bundesliga",
    "fra.1": "Ligue 1", "por.1": "Primeira Liga", "ned.1": "Eredivisie", "arg.1": "Liga Profesional (ARG)",
    "usa.1": "MLS", "uefa.champions": "UEFA Champions League", "uefa.europa": "UEFA Europa League",
    "fifa.world": "Copa do Mundo",
}


class EspnProvider:
    source = "espn"

    def __init__(self, db: DataHubDB, enabled: Optional[bool] = None):
        self.db = db
        flag = os.getenv("ENABLE_ESPN_PUBLIC_FEED", "false") if enabled is None else str(enabled)
        self._enabled = flag.strip().lower() in ("1", "true", "sim", "yes")
        self.client = PoliteHttpClient("espn", db=db, min_interval_s=2.0)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get(self, url: str, params: Dict[str, Any], max_age_s: Optional[float]) -> Dict[str, Any]:
        if not self.enabled:
            raise SourceUnavailable("Feed público da ESPN desativado (ENABLE_ESPN_PUBLIC_FEED=false).")
        return self.client.get_json(url, params=params, max_age_s=max_age_s)

    # ----------------------------------------------------------------- parse
    @staticmethod
    def parse_scoreboard_event(ev: Dict[str, Any], league: str) -> Optional[Dict[str, Any]]:
        comp = (ev.get("competitions") or [{}])[0]
        status = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        if not status.get("completed"):
            return None
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        home, away = sides.get("home", {}), sides.get("away", {})
        return {
            "match_id": to_internal_id("espn", int(ev["id"])),
            "source_match_id": str(ev["id"]),
            "competition_name": LEAGUES.get(league, league),
            "season_name": str((ev.get("season") or {}).get("year") or (ev.get("date") or "")[:4]),
            "season_id": int((ev.get("season") or {}).get("year") or 0),
            "match_date": (ev.get("date") or "")[:10],
            "home_team_name": (home.get("team") or {}).get("displayName", ""),
            "away_team_name": (away.get("team") or {}).get("displayName", ""),
            "home_score": int(home["score"]) if str(home.get("score", "")).isdigit() else None,
            "away_score": int(away["score"]) if str(away.get("score", "")).isdigit() else None,
            "stadium_name": ((comp.get("venue") or {}).get("fullName") or ""),
            "status": "FT",
            "data_source": "espn",
            "data_level": DataLevel.RESULT,
            "extra": {"espn_league": league},
        }

    @staticmethod
    def parse_summary(summary: Dict[str, Any], league: str, event_id: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        header = summary.get("header") or {}
        comp = (header.get("competitions") or [{}])[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        home, away = sides.get("home", {}), sides.get("away", {})
        record = {
            "match_id": to_internal_id("espn", int(event_id)),
            "source_match_id": str(event_id),
            "competition_name": LEAGUES.get(league, league),
            "season_name": str((header.get("season") or {}).get("year") or (comp.get("date") or "")[:4]),
            "match_date": (comp.get("date") or "")[:10],
            "home_team_name": (home.get("team") or {}).get("displayName", ""),
            "away_team_name": (away.get("team") or {}).get("displayName", ""),
            "home_score": int(home["score"]) if str(home.get("score", "")).isdigit() else None,
            "away_score": int(away["score"]) if str(away.get("score", "")).isdigit() else None,
            "stadium_name": (((summary.get("gameInfo") or {}).get("venue") or {}).get("fullName") or ""),
            "status": "FT",
            "data_source": "espn",
            "extra": {"espn_league": league},
        }
        box: Dict[str, Any] = {"team_stats": [], "lineups": [], "timeline": [], "player_stats": []}
        for t in (summary.get("boxscore") or {}).get("teams", []) or []:
            team = (t.get("team") or {}).get("displayName", "")
            for s in t.get("statistics", []) or []:
                key = ESPN_MAP.get(s.get("name"))
                row = stat_row(team, key, s.get("displayValue", s.get("value"))) if key else None
                if row:
                    box["team_stats"].append(row)
        for r in summary.get("rosters", []) or []:
            team = (r.get("team") or {}).get("displayName", "")
            formation = r.get("formation") or ""
            for p in r.get("roster", []) or []:
                ath = p.get("athlete") or {}
                if not ath.get("displayName"):
                    continue
                pos = p.get("position") or {}
                box["lineups"].append({
                    "team_name": team, "player_name": ath["displayName"], "shirt_number": str(p.get("jersey") or ""),
                    "position": pos.get("abbreviation") or pos.get("displayName") or "",
                    "is_starter": 1 if p.get("starter") else 0, "formation": formation, "coach": "",
                })
                stats = {s.get("name"): s.get("value") for s in p.get("stats", []) or [] if s.get("name")}
                if stats:
                    box["player_stats"].append({"team_name": team, "player_name": ath["displayName"],
                                                "position": pos.get("abbreviation") or "", "minutes": None,
                                                "rating": None, "stats": stats})
        for ke in summary.get("keyEvents", []) or []:
            clock = (ke.get("clock") or {}).get("displayValue", "") or ""
            digits = clock.replace("'", "").split("+")
            minute = int(digits[0]) if digits and digits[0].strip().isdigit() else None
            extra = int(digits[1]) if len(digits) > 1 and digits[1].strip().isdigit() else None
            parts = [((x.get("athlete") or {}).get("displayName") or "") for x in ke.get("participants", []) or []]
            box["timeline"].append({
                "minute": minute, "extra_minute": extra, "team_name": (ke.get("team") or {}).get("displayName", ""),
                "player_name": parts[0] if parts else "", "related_player": parts[1] if len(parts) > 1 else "",
                "event_type": ((ke.get("type") or {}).get("text") or ""), "detail": ke.get("text") or "",
            })
        record["data_level"] = DataLevel.BOXSCORE if (box["team_stats"] or box["lineups"]) else DataLevel.RESULT
        return record, box

    # ------------------------------------------------------------- consultas
    def scoreboard(self, league: str, d_from: date, d_to: date) -> List[Dict[str, Any]]:
        dates = d_from.strftime("%Y%m%d") if d_from == d_to else f"{d_from:%Y%m%d}-{d_to:%Y%m%d}"
        recent = (date.today() - d_to).days < 3
        data = self._get(f"{BASE}/{league}/scoreboard", {"dates": dates, "limit": 200},
                         max_age_s=1800 if recent else None)
        out = []
        for ev in data.get("events", []) or []:
            rec = self.parse_scoreboard_event(ev, league)
            if rec:
                out.append(rec)
        return out

    def ingest_event(self, internal_match_id: int) -> Dict[str, Any]:
        match = self.db.get_match(internal_match_id) or {}
        import json as _json

        league = (_json.loads(match.get("extra_json") or "{}") or {}).get("espn_league")
        event_id = int(internal_match_id) - 500_000_000
        if not league:
            raise SourceUnavailable("Liga ESPN desconhecida para esta partida.")
        summary = self._get(f"{BASE}/{league}/summary", {"event": event_id}, max_age_s=None)
        record, box = self.parse_summary(summary, league, event_id)
        self.db.upsert_matches([record])
        self.db.save_boxscore(record["match_id"], box)
        return record

    def sync_recent(self, days_back: int = 3, leagues: Optional[List[str]] = None) -> Dict[str, int]:
        totals = {"added": 0, "updated": 0, "errors": 0}
        today = date.today()
        for lg in leagues or list(LEAGUES):
            try:
                recs = self.scoreboard(lg, today - timedelta(days=days_back), today)
            except Exception:
                totals["errors"] += 1
                continue
            r = self.db.upsert_matches(recs)
            totals["added"] += r["added"]
            totals["updated"] += r["updated"]
        return totals
