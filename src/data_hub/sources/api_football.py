"""
API-Football (api-sports.io) — boxscore oficial com chave.

Com uma chamada `/fixtures?id=X` vêm: placar, árbitro, estádio, linha do tempo
(gols, cartões, substituições, VAR), escalações com formação e técnico, estatísticas
dos dois times e estatísticas individuais (nota, minutos, passes, finalizações...).

Plano gratuito: 100 requisições/dia (controladas pela cota do Data Hub). Relatos de
2026 indicam que a temporada atual pode exigir plano pago; temporadas anteriores
funcionam no grátis. Chave em .env: API_FOOTBALL_KEY=...
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.data_hub.boxscore import API_FOOTBALL_MAP, stat_row
from src.data_hub.db import DataHubDB
from src.data_hub.http import PoliteHttpClient, SourceUnavailable
from src.data_hub.registry import DataLevel, to_internal_id

BASE = "https://v3.football.api-sports.io"

# Ligas acompanhadas pela sincronização automática (id API-Football → nome)
TRACKED_LEAGUES: Dict[int, str] = {
    71: "Brasileirão Série A", 72: "Brasileirão Série B", 73: "Copa do Brasil",
    13: "CONMEBOL Libertadores", 11: "CONMEBOL Sul-Americana",
    39: "Premier League", 140: "La Liga", 135: "Serie A", 78: "Bundesliga", 61: "Ligue 1",
    2: "UEFA Champions League", 3: "UEFA Europa League", 1: "Copa do Mundo",
}
CALENDAR_YEAR_LEAGUES = {71, 72, 73, 13, 11, 1}
FINISHED = {"FT", "AET", "PEN"}


def season_for(league_id: Optional[int], d: date) -> int:
    if league_id in CALENDAR_YEAR_LEAGUES:
        return d.year
    return d.year if d.month >= 7 else d.year - 1


class ApiFootballProvider:
    source = "api_football"

    def __init__(self, db: DataHubDB, api_key: Optional[str] = None, daily_quota: int = 100):
        self.db = db
        self.api_key = (api_key or os.getenv("API_FOOTBALL_KEY", "")).strip()
        self.client = PoliteHttpClient(
            "api_football", db=db, min_interval_s=6.5, daily_quota=daily_quota,
            default_headers={"x-apisports-key": self.api_key},
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and "coloque" not in self.api_key.lower()

    def _get(self, path: str, params: Dict[str, Any], max_age_s: Optional[float]) -> List[Dict[str, Any]]:
        if not self.enabled:
            raise SourceUnavailable("API_FOOTBALL_KEY não configurada no .env.")
        data = self.client.get_json(f"{BASE}/{path}", params=params, max_age_s=max_age_s)
        errors = data.get("errors")
        if errors and (isinstance(errors, dict) and errors or isinstance(errors, list) and errors):
            raise SourceUnavailable(f"API-Football recusou a consulta: {errors}")
        return data.get("response", []) or []

    # --------------------------------------------------------------- parsing
    @staticmethod
    def parse_fixture(fx: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        f, lg, teams, goals = fx.get("fixture", {}), fx.get("league", {}), fx.get("teams", {}), fx.get("goals", {})
        home = (teams.get("home") or {}).get("name", "")
        away = (teams.get("away") or {}).get("name", "")
        status = (f.get("status") or {}).get("short", "")
        has_box = bool(fx.get("statistics") or fx.get("lineups") or fx.get("players"))
        record = {
            "match_id": to_internal_id("api_football", int(f["id"])),
            "source_match_id": str(f["id"]),
            "competition_id": int(lg.get("id") or 0),
            "competition_name": lg.get("name", ""),
            "season_id": int(lg.get("season") or 0),
            "season_name": str(lg.get("season") or ""),
            "country_name": lg.get("country", ""),
            "round_name": lg.get("round", ""),
            "match_date": (f.get("date") or "")[:10],
            "home_team_id": int((teams.get("home") or {}).get("id") or 0),
            "home_team_name": home,
            "away_team_id": int((teams.get("away") or {}).get("id") or 0),
            "away_team_name": away,
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "stadium_name": (f.get("venue") or {}).get("name", "") or "",
            "referee_name": f.get("referee") or "",
            "status": status,
            "data_source": "api_football",
            "data_level": DataLevel.BOXSCORE if has_box else DataLevel.RESULT,
        }
        box: Dict[str, Any] = {"team_stats": [], "lineups": [], "timeline": [], "player_stats": []}
        for block in fx.get("statistics", []) or []:
            team = (block.get("team") or {}).get("name", "")
            for s in block.get("statistics", []) or []:
                key = API_FOOTBALL_MAP.get(s.get("type"))
                row = stat_row(team, key, s.get("value")) if key else None
                if row:
                    box["team_stats"].append(row)
        for lu in fx.get("lineups", []) or []:
            team = (lu.get("team") or {}).get("name", "")
            for starter, group in ((1, lu.get("startXI") or []), (0, lu.get("substitutes") or [])):
                for item in group:
                    p = item.get("player") or {}
                    if not p.get("name"):
                        continue
                    box["lineups"].append({
                        "team_name": team, "player_name": p["name"], "shirt_number": str(p.get("number") or ""),
                        "position": p.get("pos") or "", "is_starter": starter,
                        "formation": lu.get("formation") or "", "coach": (lu.get("coach") or {}).get("name", ""),
                    })
        for ev in fx.get("events", []) or []:
            t = ev.get("time") or {}
            box["timeline"].append({
                "minute": t.get("elapsed"), "extra_minute": t.get("extra"),
                "team_name": (ev.get("team") or {}).get("name", ""),
                "player_name": (ev.get("player") or {}).get("name", ""),
                "related_player": (ev.get("assist") or {}).get("name", ""),
                "event_type": ev.get("type", ""), "detail": ev.get("detail", ""),
            })
        for block in fx.get("players", []) or []:
            team = (block.get("team") or {}).get("name", "")
            for item in block.get("players", []) or []:
                p = item.get("player") or {}
                st = (item.get("statistics") or [{}])[0]
                games = st.get("games") or {}
                flat = {
                    "goals": (st.get("goals") or {}).get("total"), "assists": (st.get("goals") or {}).get("assists"),
                    "shots_total": (st.get("shots") or {}).get("total"), "shots_on": (st.get("shots") or {}).get("on"),
                    "passes_total": (st.get("passes") or {}).get("total"), "key_passes": (st.get("passes") or {}).get("key"),
                    "pass_accuracy": (st.get("passes") or {}).get("accuracy"),
                    "tackles": (st.get("tackles") or {}).get("total"),
                    "interceptions": (st.get("tackles") or {}).get("interceptions"),
                    "duels_total": (st.get("duels") or {}).get("total"), "duels_won": (st.get("duels") or {}).get("won"),
                    "dribbles_attempts": (st.get("dribbles") or {}).get("attempts"),
                    "dribbles_success": (st.get("dribbles") or {}).get("success"),
                    "fouls_committed": (st.get("fouls") or {}).get("committed"),
                    "yellow": (st.get("cards") or {}).get("yellow"), "red": (st.get("cards") or {}).get("red"),
                }
                try:
                    rating = float(games.get("rating")) if games.get("rating") else None
                except (TypeError, ValueError):
                    rating = None
                box["player_stats"].append({
                    "team_name": team, "player_name": p.get("name", ""), "position": games.get("position") or "",
                    "minutes": games.get("minutes"), "rating": rating,
                    "stats": {k: v for k, v in flat.items() if v is not None},
                })
        return record, box

    # --------------------------------------------------------------- consultas
    def search_team_ids(self, name: str) -> List[Tuple[int, str]]:
        res = self._get("teams", {"search": name[:30]}, max_age_s=30 * 86400)
        return [(int(r["team"]["id"]), r["team"]["name"]) for r in res if r.get("team")]

    def fixtures_for_team(self, team_id: int, d_from: date, d_to: date, league_id: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"team": team_id, "from": d_from.isoformat(), "to": d_to.isoformat(),
                                  "season": season_for(league_id, d_to)}
        if league_id:
            params["league"] = league_id
        recent = (date.today() - d_to).days < 3
        return self._get("fixtures", params, max_age_s=3600 if recent else None)

    def fetch_fixture_full(self, fixture_id: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        res = self._get("fixtures", {"id": int(fixture_id)}, max_age_s=None)
        if not res:
            raise SourceUnavailable(f"Partida {fixture_id} não encontrada na API-Football.")
        record, box = self.parse_fixture(res[0])
        if record["status"] not in FINISHED:
            # jogo em andamento/futuro: não congela o cache
            self.client._cache_path(f"{BASE}/fixtures", {"id": int(fixture_id)}).unlink(missing_ok=True)
        return record, box

    def ingest_fixture(self, internal_match_id: int) -> Dict[str, Any]:
        record, box = self.fetch_fixture_full(int(internal_match_id) - 100_000_000)
        self.db.upsert_matches([record])
        self.db.save_boxscore(record["match_id"], box)
        return record

    def sync_recent(self, days_back: int = 3, leagues: Optional[Dict[int, str]] = None) -> Dict[str, int]:
        """Catálogo dos jogos encerrados nos últimos dias das ligas acompanhadas (1 req/liga)."""
        totals = {"added": 0, "updated": 0, "errors": 0}
        today = date.today()
        for lid in (leagues or TRACKED_LEAGUES):
            try:
                res = self._get("fixtures", {"league": lid, "season": season_for(lid, today),
                                             "from": (today - timedelta(days=days_back)).isoformat(),
                                             "to": today.isoformat()}, max_age_s=3 * 3600)
            except Exception:
                totals["errors"] += 1
                continue
            records = [self.parse_fixture(fx)[0] for fx in res
                       if ((fx.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
            r = self.db.upsert_matches(records)
            totals["added"] += r["added"]
            totals["updated"] += r["updated"]
        return totals


# ---------------------------------------------------------------------- classificação e calendário
def standings_frame(resp: List[Dict[str, Any]], league_name: str = "") -> "pd.DataFrame":
    import pandas as pd

    rows = []
    for item in resp or []:
        lg = item.get("league") or {}
        for group in lg.get("standings") or []:
            for t in group:
                a = t.get("all") or {}
                g = a.get("goals") or {}
                rows.append({"campeonato": league_name or lg.get("name"), "temporada": lg.get("season"),
                             "grupo": t.get("group"), "posicao": t.get("rank"), "equipe": (t.get("team") or {}).get("name"),
                             "api_football_id": (t.get("team") or {}).get("id"), "pontos": t.get("points"),
                             "jogos": a.get("played"), "vitorias": a.get("win"), "empates": a.get("draw"),
                             "derrotas": a.get("lose"), "gols_pro": g.get("for"), "gols_contra": g.get("against"),
                             "saldo": t.get("goalsDiff"), "ultimos_jogos": t.get("form")})
    return pd.DataFrame(rows)


def fixtures_frame(resp: List[Dict[str, Any]], league_name: str = "") -> "pd.DataFrame":
    import pandas as pd

    rows = []
    for fx in resp or []:
        f, lg, tm = fx.get("fixture") or {}, fx.get("league") or {}, fx.get("teams") or {}
        rows.append({"api_football_id": f.get("id"), "campeonato": league_name or lg.get("name"), "rodada": lg.get("round"),
                     "data_hora_utc": f.get("date"), "status": (f.get("status") or {}).get("short"),
                     "mandante": (tm.get("home") or {}).get("name"), "visitante": (tm.get("away") or {}).get("name"),
                     "estadio": (f.get("venue") or {}).get("name"), "arbitro": f.get("referee")})
    return pd.DataFrame(rows)


def sync_tables(provider: "ApiFootballProvider", lake, days_ahead: int = 7, progress=None) -> Dict[str, int]:
    """Classificação e próximos jogos das ligas acompanhadas (2 requisições por liga; cache de 12 h)."""
    import pandas as pd

    say = progress or (lambda m: None)
    today = date.today()
    tabs, fxs = [], []
    for lid, name in TRACKED_LEAGUES.items():
        season = season_for(lid, today)
        try:
            tabs.append(standings_frame(provider._get("standings", {"league": lid, "season": season}, 12 * 3600), name))
        except Exception as exc:
            say(f"  api-football {name}: classificação indisponível ({exc})")
        try:
            fxs.append(fixtures_frame(provider._get("fixtures", {"league": lid, "season": season, "from": today.isoformat(),
                                                                  "to": (today + timedelta(days=days_ahead)).isoformat()},
                                                    12 * 3600), name))
        except Exception as exc:
            say(f"  api-football {name}: calendário indisponível ({exc})")
    prov = dict(source="API-Football", connector="APIConnector[api-football]", license="API oficial com chave")
    out = {"tabelas": 0, "proximos_jogos": 0}
    if tabs and any(not t.empty for t in tabs):
        t = pd.concat(tabs, ignore_index=True)
        lake.write("apf_classificacao", t, **prov)
        out["tabelas"] = int(t["campeonato"].nunique())
    if fxs and any(not f.empty for f in fxs):
        f = pd.concat(fxs, ignore_index=True)
        lake.write("apf_calendario", f, **prov)
        out["proximos_jogos"] = len(f)
    out["updated"] = out["tabelas"]
    return out
