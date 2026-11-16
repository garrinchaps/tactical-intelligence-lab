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
from src.data_hub.http import ClientRefused, PoliteHttpClient, SourceUnavailable
from src.data_hub.registry import DataLevel, to_internal_id

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# v36 (B1) — cobertura em duas prioridades; códigos VALIDADOS contra a ESPN em 16/11/2026 (pedido por ano). Antes:
# não foram conferidos (a sessão na nuvem não alcança a ESPN). Código que a ESPN recusar (400/404) é pulado e a recusa
# fica lembrada por 7 dias — nada é dado como "integrado" sem ter devolvido jogos de verdade.
PRIORITY_A: Dict[str, str] = {   # Brasil, profundidade máxima
    "bra.1": "Brasileirão Série A", "bra.2": "Brasileirão Série B", "bra.3": "Brasileirão Série C",
    "bra.copa_do_brazil": "Copa do Brasil", "bra.supercopa": "Supercopa do Brasil",
    "bra.copa_do_nordeste": "Copa do Nordeste",
    "bra.camp.paulista": "Paulistão", "bra.camp.carioca": "Carioca",
    "bra.camp.mineiro": "Mineiro", "bra.camp.gaucho": "Gaúcho",
}
PRIORITY_B: Dict[str, str] = {   # exterior seletivo
    "conmebol.libertadores": "CONMEBOL Libertadores", "conmebol.sudamericana": "CONMEBOL Sul-Americana",
    "conmebol.recopa": "Recopa Sul-Americana", "arg.1": "Liga Profesional (ARG)", "uru.1": "Uruguai",
    "chi.1": "Chile", "col.1": "Colômbia", "par.1": "Paraguai",
    "ecu.1": "Equador", "per.1": "Peru", "bol.1": "Bolívia",
    "conmebol.america": "Copa América", "fifa.worldq.conmebol": "Eliminatórias CONMEBOL",
    "uefa.champions": "UEFA Champions League", "uefa.europa": "UEFA Europa League",
    "uefa.europa.conf": "UEFA Conference League", "eng.1": "Premier League", "eng.2": "Championship",
    "esp.1": "La Liga", "esp.2": "La Liga 2", "ger.1": "Bundesliga", "ger.2": "2. Bundesliga",
    "ita.1": "Serie A", "ita.2": "Serie B (ITA)", "fra.1": "Ligue 1", "fra.2": "Ligue 2",
    "ned.1": "Eredivisie", "por.1": "Primeira Liga", "bel.1": "Bélgica", "tur.1": "Turquia",
    "sco.1": "Escócia", "uefa.euro": "Eurocopa", "uefa.nations": "Nations League",
    "usa.1": "MLS", "mex.1": "Liga MX", "concacaf.leagues.cup": "Leagues Cup",
    "afc.champions": "Champions Asiática", "jpn.1": "J1 League", "kor.1": "K League",
    "ksa.1": "Saudi Pro League", "caf.champions": "CAF Champions League",
    "aus.1": "A-League", "fifa.world": "Copa do Mundo", "fifa.cwc": "Mundial de Clubes",
}
LEAGUES: Dict[str, str] = {**PRIORITY_A, **PRIORITY_B}
# validado em 16/11/2026 (pedido por ano): fora da ESPN → bra.supercopa, kor.1; Série C 2026 vem vazia
for _bad in ("bra.supercopa", "kor.1"):
    LEAGUES.pop(_bad, None)
    PRIORITY_A.pop(_bad, None)
    PRIORITY_B.pop(_bad, None)
# ordem dos resumos (estatísticas + escalações): Brasil e Europa principal primeiro
SUMMARY_PRIORITY = ["bra.1", "bra.2", "bra.copa_do_brazil", "conmebol.libertadores", "conmebol.sudamericana",
                    "uefa.champions", "eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "bra.copa_do_nordeste",
                    "bra.camp.paulista", "bra.camp.carioca", "bra.camp.mineiro", "bra.camp.gaucho", "bra.3",
                    "uefa.europa", "uefa.europa.conf", "por.1", "ned.1", "arg.1", "usa.1", "mex.1", "ksa.1", "eng.2",
                    "esp.2", "ita.2", "ger.2", "fra.2", "bel.1", "tur.1", "sco.1", "uefa.nations", "fifa.world"]
ROSTER_LEAGUES = ["bra.1", "bra.2", "esp.1", "eng.1", "ita.1", "ger.1", "fra.1", "por.1", "arg.1"]
LEAGUE_NAMES = {k: v.replace("", "") for k, v in LEAGUES.items()}


class EspnProvider:
    source = "espn"

    def __init__(self, db: DataHubDB, enabled: Optional[bool] = None):
        self.db = db
        # v36: a ESPN virou a fonte principal da temporada atual (2025/2026); ligada por padrão, desligável no .env
        flag = os.getenv("ENABLE_ESPN_PUBLIC_FEED", "true") if enabled is None else str(enabled)
        self._enabled = flag.strip().lower() in ("1", "true", "sim", "yes")
        self.client = PoliteHttpClient("espn", db=db, min_interval_s=1.0)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get(self, url: str, params: Dict[str, Any], max_age_s: Optional[float]) -> Dict[str, Any]:
        if not self.enabled:
            raise SourceUnavailable("Feed público da ESPN desativado (ENABLE_ESPN_PUBLIC_FEED=false).")
        return self.client.get_json(url, params=params, max_age_s=max_age_s)

    # ----------------------------------------------------------------- parse
    @staticmethod
    def parse_scoreboard_event(ev: Dict[str, Any], league: str, include_live: bool = False) -> Optional[Dict[str, Any]]:
        comp = (ev.get("competitions") or [{}])[0]
        status = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        live = status.get("state") == "in" or str(status.get("name", "")).upper() in (
            "STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_FIRST_HALF", "STATUS_SECOND_HALF", "STATUS_EXTRA_TIME")
        if not status.get("completed") and not (include_live and live):
            return None
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        home, away = sides.get("home", {}), sides.get("away", {})
        return {
            "match_id": to_internal_id("espn", int(ev["id"])),
            "source_match_id": str(ev["id"]),
            "competition_name": LEAGUE_NAMES.get(league, league),
            "season_name": str((ev.get("season") or {}).get("year") or (ev.get("date") or "")[:4]),
            "season_id": int((ev.get("season") or {}).get("year") or 0),
            "match_date": (ev.get("date") or "")[:10],
            "home_team_name": (home.get("team") or {}).get("displayName", ""),
            "away_team_name": (away.get("team") or {}).get("displayName", ""),
            "home_team_id": int((home.get("team") or {}).get("id") or 0),
            "away_team_id": int((away.get("team") or {}).get("id") or 0),
            "home_score": int(home["score"]) if str(home.get("score", "")).isdigit() else None,
            "away_score": int(away["score"]) if str(away.get("score", "")).isdigit() else None,
            "stadium_name": ((comp.get("venue") or {}).get("fullName") or ""),
            "status": "FT" if status.get("completed") else "LIVE",
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
            "competition_name": LEAGUE_NAMES.get(league, league),
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
    # ------------------------------------------------------------- consultas
    # v36: a ESPN passou a RECUSAR intervalos de datas ("20251001-20251007" → HTTP 400 em todas as ligas).
    # Aceita um dia ("20251004"), um mês ("202510") ou um ano ("2025"). Por isso tudo é pedido por ano ou mês.
    def _events(self, league: str, dates: str, recent: bool) -> List[Dict[str, Any]]:
        data = self._get(f"{BASE}/{league}/scoreboard", {"dates": dates, "limit": 1000},
                         max_age_s=1800 if recent else None)
        return data.get("events", []) or []

    def season_events(self, league: str, year: int) -> List[Dict[str, Any]]:
        """Todos os jogos da liga no ano civil (1 pedido; se vier cheio, mês a mês)."""
        recent = year >= date.today().year
        evs = self._events(league, str(year), recent)
        if len(evs) >= 1000:
            evs = []
            for m in range(1, 13):
                evs += self._events(league, f"{year}{m:02d}", recent and m >= date.today().month - 1)
        return evs

    def scoreboard(self, league: str, d_from: date, d_to: date) -> List[Dict[str, Any]]:
        """Jogos ENCERRADOS entre d_from e d_to (pedidos por mês, filtrados pela data)."""
        out, seen = [], set()
        y, m = d_from.year, d_from.month
        while (y, m) <= (d_to.year, d_to.month):
            recent = (date.today() - date(y, m, 1)).days < 40
            for ev in self._events(league, f"{y}{m:02d}", recent):
                rec = self.parse_scoreboard_event(ev, league)
                if rec and d_from.isoformat() <= rec["match_date"] <= d_to.isoformat() and rec["match_id"] not in seen:
                    seen.add(rec["match_id"])
                    out.append(rec)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    @staticmethod
    def parse_fixture(ev: Dict[str, Any], league: str) -> Optional[Dict[str, Any]]:
        """Jogo futuro (ainda não começou): vai para a tabela `fixtures`, nunca para o catálogo de jogos jogados."""
        comp = (ev.get("competitions") or [{}])[0]
        st = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        if st.get("completed") or st.get("state") == "in":
            return None
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        h, a = (sides.get("home") or {}).get("team") or {}, (sides.get("away") or {}).get("team") or {}
        return {"match_id": to_internal_id("espn", int(ev["id"])), "league": league,
                "competition": LEAGUE_NAMES.get(league, league), "kickoff": ev.get("date") or "",
                "home": h.get("displayName", ""), "away": a.get("displayName", ""),
                "home_id": int(h.get("id") or 0), "away_id": int(a.get("id") or 0),
                "status": st.get("name") or "STATUS_SCHEDULED", "venue": (comp.get("venue") or {}).get("fullName") or ""}

    def save_fixtures(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        cols = ["match_id", "league", "competition", "kickoff", "home", "away", "home_id", "away_id", "status", "venue"]
        with self.db.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS fixtures (match_id INTEGER PRIMARY KEY, league TEXT, competition TEXT, "
                         "kickoff TEXT, home TEXT, away TEXT, home_id INTEGER, away_id INTEGER, status TEXT, venue TEXT, "
                         "updated_at TEXT DEFAULT (datetime('now')))")
            conn.executemany(f"INSERT OR REPLACE INTO fixtures ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                             [tuple(r[c] for c in cols) for r in rows])
            # jogo que já aconteceu sai da lista de próximos
            conn.execute("DELETE FROM fixtures WHERE match_id IN (SELECT match_id FROM matches WHERE home_score IS NOT NULL)")
        return len(rows)

    def sync_season(self, leagues: Optional[List[str]] = None, years: Optional[List[int]] = None,
                    progress=None) -> Dict[str, int]:
        """
        Resultados e calendário da temporada (padrão: ano passado e o atual) de TODAS as ligas acompanhadas:
        ~1 pedido por liga e ano. Jogos encerrados entram no catálogo; futuros vão para `fixtures`.
        """
        say = progress or (lambda m: None)
        years = years or [date.today().year - 1, date.today().year]
        tot = {"added": 0, "updated": 0, "errors": 0, "fixtures": 0, "ligas": 0}
        for lg in leagues or list(LEAGUES):
            done, fut = [], []
            for y in years:
                try:
                    evs = self.season_events(lg, y)
                except Exception as exc:
                    tot["errors"] += 1
                    say(f"  espn {lg} {y}: {exc}")
                    continue
                for ev in evs:
                    r = self.parse_scoreboard_event(ev, lg)
                    if r:
                        done.append(r)
                    else:
                        f = self.parse_fixture(ev, lg)
                        if f:
                            fut.append(f)
            if done:
                r = self.db.upsert_matches(done)
                tot["added"] += r["added"]
                tot["updated"] += r["updated"]
            tot["fixtures"] += self.save_fixtures(fut)
            tot["ligas"] += 1
            say(f"  {LEAGUE_NAMES.get(lg, lg)}: {len(done)} jogos encerrados, {len(fut)} próximos")
        return tot

    def fetch_summaries(self, leagues: Optional[List[str]] = None, since: Optional[str] = None, limit: int = 500,
                        progress=None) -> Dict[str, int]:
        """
        Resumo (estatísticas dos times, escalações com posição, números por jogador, lances principais) dos jogos
        encerrados que ainda não têm, em ORDEM DE PRIORIDADE (Brasil e Europa principal primeiro) e do mais recente
        para o mais antigo. `limit` = pedidos nesta rodada; a próxima continua de onde parou.
        """
        say = progress or (lambda m: None)
        leagues = leagues or SUMMARY_PRIORITY
        since = since or f"{date.today().year - 1}-01-01"
        ph = ",".join("?" * len(leagues))
        q = (f"SELECT m.match_id, json_extract(m.extra_json, '$.espn_league') AS lg, m.match_date FROM matches m "
             f"WHERE m.data_source = 'espn' AND m.home_score IS NOT NULL AND m.match_date >= ? "
             f"AND json_extract(m.extra_json, '$.espn_league') IN ({ph}) "
             f"AND m.match_id NOT IN (SELECT DISTINCT match_id FROM match_team_stats) ORDER BY m.match_date DESC")
        with self.db.connect() as conn:
            todo = conn.execute(q, [since, *leagues]).fetchall()
        rank = {lg: i for i, lg in enumerate(leagues)}
        todo.sort(key=lambda r: (rank.get(r[1], 99), r[2] and -int(r[2].replace("-", "")[:8] or 0)))
        tot = {"resumos": 0, "errors": 0, "pendentes": max(len(todo) - limit, 0)}
        for i, (mid, lg, d) in enumerate(todo[:limit], 1):
            try:
                self.ingest_event(int(mid))
                tot["resumos"] += 1
            except Exception as exc:
                tot["errors"] += 1
                say(f"  espn resumo {mid}: {exc}")
            if i % 50 == 0:
                say(f"  resumos: {i}/{min(limit, len(todo))}")
        say(f"  resumos baixados: {tot['resumos']} · ainda faltam {tot['pendentes']} (rode de novo para continuar)")
        return tot

    def preview(self, match_id: int, league: str, names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Pré-jogo de uma partida FUTURA: escalação OFICIAL (a ESPN publica ~1 h antes; antes disso vem vazia) e notícias
        que citam os clubes ou seus jogadores (marcadas como notícia, não como dado confirmado). Cache de 15 min.
        """
        ev_id = int(match_id) - 500_000_000
        try:
            s = self._get(f"{BASE}/{league}/summary", {"event": ev_id}, max_age_s=900)
        except Exception as exc:
            return {"oficial": {}, "noticias": [], "erro": str(exc)}
        oficial: Dict[str, Any] = {}
        for r in s.get("rosters", []) or []:
            team = (r.get("team") or {}).get("displayName", "")
            xi = [{"jogador": (p.get("athlete") or {}).get("displayName", ""), "pos": (p.get("position") or {}).get("abbreviation", ""),
                   "titular": bool(p.get("starter"))} for p in r.get("roster", []) or []]
            if any(x["titular"] for x in xi):
                oficial[team] = {"formacao": r.get("formation") or "", "jogadores": xi}
        keys = [k.lower() for k in (names or []) if k and len(k) >= 4]
        news = []
        arts = (s.get("news") or {}).get("articles", []) if isinstance(s.get("news"), dict) else []
        for a in arts:
            txt = f"{a.get('headline', '')} {a.get('description', '')}".lower()
            if not keys or any(k in txt for k in keys):
                news.append({"titulo": a.get("headline", ""), "resumo": (a.get("description") or "")[:240],
                             "data": (a.get("published") or "")[:10]})
        return {"oficial": oficial, "noticias": news[:6]}

    def team_ids(self, league: str) -> Dict[str, int]:
        data = self._get(f"{BASE}/{league}/teams", {"limit": 100}, max_age_s=7 * 24 * 3600)
        teams = ((data.get("sports") or [{}])[0].get("leagues") or [{}])[0].get("teams") or []
        return {(t.get("team") or {}).get("displayName", ""): int((t.get("team") or {}).get("id") or 0) for t in teams}

    def sync_rosters(self, leagues: Optional[List[str]] = None, progress=None) -> Dict[str, int]:
        """
        Elenco ATUAL de cada clube (ESPN): nome, nascimento, nacionalidade, posição, camisa, situação e LESÕES.
        É a referência para transferências e desfalques; guardado em `espn_rosters` (substitui o do clube a cada busca).
        """
        import json as _json

        say = progress or (lambda m: None)
        tot = {"clubes": 0, "jogadores": 0, "errors": 0, "lesionados": 0}
        with self.db.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS espn_rosters (team_id INTEGER, team TEXT, league TEXT, athlete_id INTEGER, "
                         "name TEXT, birth TEXT, citizenship TEXT, position TEXT, jersey TEXT, status TEXT, injuries TEXT, "
                         "fetched_at TEXT, PRIMARY KEY (team_id, athlete_id))")
        for lg in leagues or ROSTER_LEAGUES:
            try:
                ids = self.team_ids(lg)
            except Exception as exc:
                tot["errors"] += 1
                say(f"  espn elencos {lg}: {exc}")
                continue
            for team, tid in ids.items():
                try:
                    data = self._get(f"{BASE}/{lg}/teams/{tid}/roster", {}, max_age_s=20 * 3600)
                except Exception:
                    tot["errors"] += 1
                    continue
                rows = []
                for a in data.get("athletes", []) or []:
                    inj = a.get("injuries") or []
                    tot["lesionados"] += 1 if inj else 0
                    rows.append((tid, team, lg, int(a.get("id") or 0), a.get("displayName") or "",
                                 (a.get("dateOfBirth") or "")[:10], a.get("citizenship") or "",
                                 (a.get("position") or {}).get("abbreviation") or "", str(a.get("jersey") or ""),
                                 ((a.get("status") or {}).get("name") or ""), _json.dumps(inj, ensure_ascii=False)[:2000],
                                 date.today().isoformat()))
                with self.db.connect() as conn:
                    conn.execute("DELETE FROM espn_rosters WHERE team_id = ?", (tid,))
                    conn.executemany("INSERT OR REPLACE INTO espn_rosters VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                tot["clubes"] += 1
                tot["jogadores"] += len(rows)
            say(f"  {LEAGUE_NAMES.get(lg, lg)}: elencos atualizados")
        return tot

    def ingest_event(self, internal_match_id: int) -> Dict[str, Any]:
        from src.data_hub import sync_policy as P

        if P.is_frozen(self.db, internal_match_id) and self.db.has_boxscore(int(internal_match_id)):
            return self.db.get_match(internal_match_id) or {}       # B2: encerrada e consolidada — não baixa de novo
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
        if record.get("status") == "FT" and (box["team_stats"] or box["lineups"]):
            P.freeze(self.db, [record["match_id"]])                 # consolidação final feita: congela
        return record

    def backfill(self, leagues: Optional[List[str]] = None, since_year: int = 2018, until: Optional[date] = None,
                 max_summaries: Optional[int] = None, progress=None) -> Dict[str, int]:
        """
        Histórico: um pedido por liga e ANO (a ESPN não aceita mais intervalos de datas). Depois baixa os resumos
        (estatísticas, escalações) dos jogos sem números, na ordem de prioridade, até `max_summaries`.
        """
        say = progress or (lambda m: None)
        until = until or date.today()
        leagues = leagues or list(PRIORITY_A) + ["conmebol.libertadores", "conmebol.sudamericana"]
        tot = {"added": 0, "updated": 0, "errors": 0, "resumos": 0, "anos": 0, "janelas_falhas": 0}
        for lg in leagues:
            empty_years = 0
            for y in range(until.year, since_year - 1, -1):          # do mais recente para trás
                try:
                    evs = self.season_events(lg, y)
                except Exception as exc:
                    tot["errors"] += 1
                    tot["janelas_falhas"] += 1
                    say(f"  espn {lg} {y}: {exc}")
                    continue
                tot["anos"] += 1
                recs = [r for r in (self.parse_scoreboard_event(ev, lg) for ev in evs) if r and r["match_date"] <= until.isoformat()]
                say(f"  {LEAGUE_NAMES.get(lg, lg)} {y}: {len(recs)} jogos")
                if not recs:
                    empty_years += 1
                    if empty_years >= 2:                        # dois anos seguidos sem jogos: a ESPN não tem mais
                        say(f"  {LEAGUE_NAMES.get(lg, lg)}: sem jogos antes de {y + 2} na ESPN")
                        break
                    continue
                empty_years = 0
                r = self.db.upsert_matches(recs)
                tot["added"] += r["added"]
                tot["updated"] += r["updated"]
                todo = [x for x in recs if not self.db.has_boxscore(int(x["match_id"]))]
                for x in todo:
                    if max_summaries is not None and tot["resumos"] >= max_summaries:
                        return tot
                    try:
                        self.ingest_event(int(x["match_id"]))
                        tot["resumos"] += 1
                    except Exception as exc:
                        tot["errors"] += 1
                        say(f"  espn resumo {x['home_team_name']} x {x['away_team_name']}: {exc}")
        return tot

    def sync_recent(self, days_back: int = 3, leagues: Optional[List[str]] = None, summaries: int = 200) -> Dict[str, int]:
        """
        Atualização automática (a cada poucas horas): temporada do ano corrente de todas as ligas (1 pedido por liga,
        com cache de 30 min) — resultados novos entram, fixtures são atualizadas — e os resumos dos jogos encerrados
        na última semana (estatísticas + escalações), dentro de `summaries` pedidos.
        """
        from src.data_hub import sync_policy as P

        lgs = leagues or list(LEAGUES)
        tot = self.sync_season(lgs, [date.today().year])
        for lg in lgs:
            P.mark_synced(self.db, "espn", lg)
        if summaries:
            s = self.fetch_summaries([l for l in SUMMARY_PRIORITY if l in lgs] or lgs,
                                     since=(date.today() - timedelta(days=max(days_back, 7))).isoformat(), limit=summaries)
            tot["resumos"] = s["resumos"]
        return tot

    def live_tick(self, leagues: Optional[List[str]] = None) -> Dict[str, int]:
        """
        B2: placar ao vivo (chamado a cada minuto enquanto houver jogo em andamento). Jogo que acabou recebe a
        consolidação final (resumo com estatísticas) e é congelado. Fixture futura não é buscada aqui.
        """
        from src.data_hub import sync_policy as P

        out = {"ao_vivo": 0, "encerrados": 0, "errors": 0, "ligas_ao_vivo": []}
        today = date.today()
        for lg in leagues or list(LEAGUES):
            try:
                data = self._get(f"{BASE}/{lg}/scoreboard", {"dates": f"{today:%Y%m%d}"}, max_age_s=50)
            except Exception:
                out["errors"] += 1
                continue
            recs = [r for r in (self.parse_scoreboard_event(ev, lg, include_live=True)
                                for ev in data.get("events", []) or []) if r]
            if not recs:
                continue
            self.db.upsert_matches(recs)
            for r in recs:
                if r["status"] == "LIVE":
                    out["ao_vivo"] += 1
                    if lg not in out["ligas_ao_vivo"]:
                        out["ligas_ao_vivo"].append(lg)
                elif not P.is_frozen(self.db, r["match_id"]):
                    try:
                        self.ingest_event(int(r["match_id"]))
                        out["encerrados"] += 1
                    except Exception:
                        out["errors"] += 1
        return out
