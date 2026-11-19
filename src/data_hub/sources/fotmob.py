"""
FotMob (rodada 5) — fonte complementar à ESPN, com cobertura muito maior e dados mais ricos por jogo.

O que a FotMob dá, sem chave (endpoints JSON públicos do próprio site, `/api/data/...`):
  * calendário e resultados de centenas de competições, com temporadas anteriores (Série A–D, estaduais, Copa do
    Nordeste, ligas femininas, Libertadores, Sul-Americana, 2ª divisões europeias…);
  * por jogo: estatísticas dos times (inclui xG, xG de bola parada, xGOT, toques na área e — só onde a liga mede —
    distância percorrida e sprints), escalação com a POSIÇÃO EXATA no desenho, números por jogador (minutos, xG, xA,
    passes, duelos, nota da FotMob, distância/velocidade máxima quando medidas), mapa de finalizações com coordenadas
    e xG, cartões, gols e substituições, desfalques com previsão de volta.

Regras honestas:
  * a nota por jogador é a da FotMob (guardada como nota da fonte, nunca misturada com a nota do laboratório);
  * xG é o modelo da FotMob (Opta) — não é comparável sem aviso com o xG de outra fonte;
  * distância/sprints só existem onde a liga mede (ex.: Premier League); ausência NÃO vira zero;
  * finalizações vão para `match_shots` (não para `events`): ter o mapa de chutes não é ter todos os lances.

Uso responsável: é o site da FotMob, não uma API contratada — uso pessoal, devagar (1 pedido a cada 1,5 s), com
retomada (não baixa de novo o que já tem). Pelo comando (`--only fotmob...`) roda quando você manda; a atualização
automática do app só usa a FotMob se você puser `ENABLE_FOTMOB=true` no .env (`ENABLE_FOTMOB=false` desliga tudo).
Os termos de uso da FotMob não autorizam uso comercial dos dados.
"""

from __future__ import annotations

import os
import time
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.data_hub.boxscore import stat_row
from src.data_hub.db import DataHubDB
from src.data_hub.http import PoliteHttpClient, SourceUnavailable
from src.data_hub.registry import DataLevel, to_internal_id

BASE = "https://www.fotmob.com/api/data"

# id da liga na FotMob → nome usado no laboratório (conferidos em /api/data/allLeagues em 16/11/2026)
LEAGUES: Dict[int, str] = {
    # Brasil
    268: "Brasileirão Série A", 8814: "Brasileirão Série B", 8971: "Brasileirão Série C", 9464: "Brasileirão Série D",
    9067: "Copa do Brasil", 10077: "Supercopa do Brasil", 9429: "Copa do Nordeste", 10244: "Paulistão A1",
    9483: "Paulistão A2", 10272: "Carioca", 10273: "Mineiro", 10274: "Gaúcho", 10290: "Baiano", 10291: "Goiano",
    # América do Sul
    45: "CONMEBOL Libertadores", 299: "CONMEBOL Sul-Americana", 491: "Recopa Sul-Americana", 44: "Copa América",
    11021: "Libertadores Feminina", 112: "Argentina — Liga Profesional", 8965: "Argentina — Primera Nacional",
    9305: "Copa Argentina", 161: "Uruguai — Primera División", 9122: "Uruguai — Segunda División",
    273: "Chile — Primera División", 9126: "Chile — Primera B", 274: "Colômbia — Primera A", 9125: "Colômbia — Primera B",
    246: "Equador — LigaPro Serie A", 199: "Paraguai — Primera División", 131: "Peru — Liga 1",
    144: "Bolívia — División Profesional", 339: "Venezuela — Primera División",
    # Europa (1ª e 2ª divisões + copas)
    47: "Premier League", 48: "Championship", 132: "FA Cup", 133: "EFL Cup", 87: "La Liga", 140: "La Liga 2",
    138: "Copa del Rey", 54: "Bundesliga", 146: "2. Bundesliga", 209: "DFB-Pokal", 55: "Serie A", 86: "Serie B",
    141: "Coppa Italia", 53: "Ligue 1", 110: "Ligue 2", 134: "Coupe de France", 61: "Primeira Liga",
    185: "Liga Portugal 2", 186: "Taça de Portugal", 57: "Eredivisie", 111: "Eerste Divisie", 235: "KNVB Beker",
    40: "Bélgica — Pro League", 264: "Bélgica — Challenger Pro League", 149: "Copa da Bélgica", 71: "Süper Lig",
    165: "Turquia — 1. Lig", 151: "Copa da Turquia", 64: "Escócia — Premiership", 123: "Escócia — Championship",
    38: "Áustria — Bundesliga", 69: "Suíça — Super League", 135: "Grécia — Super League", 46: "Dinamarca — Superligaen",
    59: "Noruega — Eliteserien", 67: "Suécia — Allsvenskan", 252: "Croácia — HNL", 182: "Sérvia — Super Liga",
    196: "Polônia — Ekstraklasa", 122: "Tchéquia — 1. Liga", 441: "Ucrânia — Premier League",
    # UEFA, FIFA e seleções
    114: "Amistosos internacionais",
    42: "UEFA Champions League", 73: "UEFA Europa League", 10216: "UEFA Conference League", 74: "Supercopa da UEFA",
    50: "Eurocopa", 10607: "Eliminatórias da Eurocopa", 9806: "Liga das Nações A", 78: "Mundial de Clubes",
    # feminino
    9375: "Champions League Feminina", 9907: "Liga F (Espanha)", 9676: "Frauen-Bundesliga", 9677: "Première Ligue (França)",
    10178: "Serie A Femminile",
    # outras Américas
    130: "MLS", 230: "Liga MX",
    # rodada 20: mercados que faltavam (Zenit/Rússia, Arábia, Japão, Coreia, Catar, Emirados, Romênia, Israel, Hungria,
    # Bulgária, China, Austrália, 2ª do México) — ids conferidos em /api/data/allLeagues (19/11/2026)
    63: "Rússia — Premier Liga", 536: "Arábia Saudita — Saudi Pro League", 223: "Japão — J1 League",
    9080: "Coreia do Sul — K League 1", 535: "Catar — Stars League", 538: "Emirados — Pro League",
    189: "Romênia — Liga I", 127: "Israel — Ligat ha'Al", 212: "Hungria — NB I", 270: "Bulgária — First League",
    120: "China — Super League", 113: "Austrália — A-League", 8976: "México — Liga de Expansión",
    # rodada 20: seleções de base (critério de PROMESSA no Scout) — ids conferidos em /api/data/allLeagues (19/11/2026)
    296: "Copa do Mundo Sub-20", 306: "Copa do Mundo Sub-17", 9848: "Sul-Americano Sub-20", 288: "Eurocopa Sub-21",
    301: "Eurocopa Sub-17", 287: "Eurocopa Sub-19", 11022: "Libertadores Sub-20",
}
YOUTH_LEAGUES = [296, 306, 9848, 288, 301, 287]          # seleções (a Libertadores Sub-20 é de clubes)
YOUTH_NAMES = {LEAGUES[i] for i in YOUTH_LEAGUES}
# ordem de prioridade para baixar detalhes: Brasil e Europa principal primeiro
PRIORITY = [268, 8814, 8971, 9067, 45, 299, 47, 87, 54, 55, 53, 42, 61, 57, 9464, 73, 10216, 112,
            # rodada 14: ligas sul-americanas logo depois do Brasil/Argentina/Europa principal (mercado do Scout)
            199, 161, 273, 274, 246, 131, 144, 339,
            48, 140, 146, 86, 110, 71, 40, 64, 114, 9429, 10244, 10272, 10273, 10274]
REGIONS = {  # atalhos para `--ligas` (sync) e para o Scout pedir uma região inteira
    "sulamericanas": [112, 199, 161, 273, 274, 246, 131, 144, 339, 9305],
    "brasil": [268, 8814, 8971, 9067],
    "base": [296, 306, 9848, 288, 301, 287, 11022],        # rodada 20: seleções de base + Libertadores Sub-20
}

STAT_MAP = {  # chave da FotMob → chave interna
    "BallPossesion": "possession_pct", "expected_goals": "xg", "expected_goals_open_play": "xg_open_play",
    "expected_goals_set_play": "xg_set_play", "expected_goals_non_penalty": "npxg", "expected_goals_on_target": "xgot",
    "total_shots": "shots_total", "ShotsOnTarget": "shots_on_target", "ShotsOffTarget": "shots_off_target",
    "blocked_shots": "shots_blocked", "shots_woodwork": "woodwork", "shots_inside_box": "shots_inside_box",
    "shots_outside_box": "shots_outside_box", "big_chance": "big_chances", "big_chance_missed_title": "big_chances_missed",
    "touches_opp_box": "touches_opp_box", "passes": "passes_total", "accurate_passes": "passes_accurate",
    "own_half_passes": "passes_own_half", "opposition_half_passes": "passes_opp_half",
    "long_balls_accurate": "long_balls_accurate", "accurate_crosses": "crosses_accurate", "player_throws": "throw_ins",
    "Offsides": "offsides", "corners": "corners", "matchstats.headers.tackles": "tackles_won",
    "interceptions": "interceptions", "shot_blocks": "blocks", "clearances": "clearances", "keeper_saves": "saves",
    "duel_won": "duels_won", "ground_duels_won": "ground_duels_won", "aerials_won": "aerials_won",
    "dribbles_succeeded": "dribbles_completed", "yellow_cards": "yellow_cards", "red_cards": "red_cards", "fouls": "fouls",
    "physical_metrics_distance_covered": "distance_m", "physical_metrics_running": "running_m",
    "physical_metrics_sprinting": "sprinting_m", "physical_metrics_number_of_sprints": "sprints",
}
# números por jogador: chave da FotMob → nome usado pelas telas (padrão ESPN para os básicos)
PLAYER_MAP = {"goals": "totalGoals", "assists": "goalAssists", "total_shots": "totalShots", "ShotsOnTarget": "shotsOnTarget",
              "fouls": "foulsCommitted", "saves": "saves", "minutes_played": "minutes", "expected_goals": "xg",
              "expected_assists": "xa", "chances_created": "chances_created", "touches": "touches",
              "physical_metrics_distance_covered": "distance_m", "physical_metrics_topspeed": "top_speed_kmh",
              "errors_led_to_goal": "errors_led_to_goal", "defensive_actions": "defensive_actions",
              "physical_metrics_number_of_sprints": "sprints", "expected_goals_on_target_faced": "xgot_faced",
              "yellow_cards": "yellow_cards", "red_cards": "red_cards"}
GENERIC_POS = {0: "G", 1: "D", 2: "M", 3: "F"}
DROP_KEYS = {"fantasy_points", "xg_and_xa", "rating_title"}       # redundantes (somas, pontos de fantasy)


def _season_label(raw: Any) -> str:
    return str(raw or "").replace("/", "-")


def layout_role(p: Dict[str, Any], formation: str) -> Optional[str]:
    """
    Posição exata pelo lugar do jogador no desenho (horizontalLayout: x = profundidade 0→1, y = largura com 1 = DIREITA)
    e pelo código `positionId` (dezena = linha, unidade = coluna). Sem layout, devolve None (fica a posição genérica).
    """
    lay = p.get("horizontalLayout") or {}
    if not lay or p.get("positionId") in (None, 1000):
        return None
    x, y = float(lay.get("x", 0)), float(lay.get("y", 0.5))
    pid = int(p.get("positionId") or 0)
    line = pid // 10
    wide_r, wide_l = y >= 0.78, y <= 0.22
    lines = [int(c) for c in re.findall(r"\d", formation or "")]
    back3 = bool(lines) and lines[0] in (3, 5)
    if line <= 1 or x <= 0.15:
        return "GK"
    if x < 0.4:                                            # linha de defesa
        if back3 and lines[0] == 5 and (wide_r or wide_l):
            return "RWB" if wide_r else "LWB"
        return "RB" if wide_r else "LB" if wide_l else "CB"
    if x < 0.6:                                            # primeira linha do meio
        if wide_r or wide_l:
            return ("RWB" if wide_r else "LWB") if back3 else ("RM" if wide_r else "LM")
        deep_line = len(lines) >= 4 or (len(lines) == 3 and lines[1] in (1, 2) and x < 0.52)
        return "DM" if deep_line or x < 0.45 else "CM"
    if x < 0.8:                                            # meia-ofensiva / pontas recuados
        if wide_r or wide_l:
            return "RW" if wide_r else "LW"
        return "AM"
    if wide_r or wide_l:
        return "RW" if wide_r else "LW"
    return "ST"


class FotmobProvider:
    source = "fotmob"

    def __init__(self, db: DataHubDB, enabled: Optional[bool] = None):
        self.db = db
        flag = os.getenv("ENABLE_FOTMOB", "true") if enabled is None else str(enabled)
        self._enabled = flag.strip().lower() in ("1", "true", "sim", "yes")
        # ~0,7 s entre pedidos (≈ 5 mil jogos por hora): rápido, mas sem rajadas; FOTMOB_INTERVALO no .env ajusta
        try:
            gap = max(float(os.getenv("FOTMOB_INTERVALO", "0.7")), 0.3)
        except ValueError:
            gap = 0.7
        self.client = PoliteHttpClient("fotmob", db=db, min_interval_s=gap)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get(self, path: str, params: Dict[str, Any], max_age_s: Optional[float], cache: bool = True) -> Dict[str, Any]:
        if not self.enabled:
            raise SourceUnavailable("FotMob desligada (ENABLE_FOTMOB=false).")
        return self.client.get_json(f"{BASE}/{path}", params=params, max_age_s=max_age_s, use_cache=cache)

    # ------------------------------------------------------------------ calendário
    def league(self, league_id: int, season: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"id": int(league_id)}
        if season:
            params["season"] = season
        # temporada passada não muda: cache permanente; a atual, 3 h
        return self._get("leagues", params, max_age_s=None if season and not self._is_current(season) else 3 * 3600)

    @staticmethod
    def _is_current(season: str) -> bool:
        y = date.today().year
        return str(y) in season or str(y - 1) + "/" in season and date.today().month <= 7

    @staticmethod
    def parse_match(m: Dict[str, Any], league_id: int, season: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """(partida encerrada, jogo futuro) a partir de um item de `fixtures.allMatches`."""
        st = m.get("status") or {}
        mid = to_internal_id("fotmob", int(m["id"]))
        home, away = m.get("home") or {}, m.get("away") or {}
        comp = LEAGUES.get(int(league_id), str(league_id))
        when = str(st.get("utcTime") or "")
        if st.get("cancelled"):
            return None, None
        if st.get("finished"):
            score = str(st.get("scoreStr") or "")
            hs = as_ = None
            mm = re.match(r"\s*(\d+)\s*-\s*(\d+)", score)
            if mm:
                hs, as_ = int(mm.group(1)), int(mm.group(2))
            elif home.get("score") is not None:
                hs, as_ = int(home["score"]), int(away.get("score"))
            return {"match_id": mid, "source_match_id": str(m["id"]), "competition_name": comp,
                    "season_name": _season_label(season), "match_date": when[:10],
                    "home_team_name": home.get("name", ""), "away_team_name": away.get("name", ""),
                    "home_score": hs, "away_score": as_, "status": "FT", "data_source": "fotmob",
                    "data_level": DataLevel.RESULT, "extra": {"fotmob_league": int(league_id), "round": m.get("round")}}, None
        if st.get("started"):
            return None, None
        return None, {"match_id": mid, "league": f"fotmob:{league_id}", "competition": comp, "kickoff": when,
                      "home": home.get("name", ""), "away": away.get("name", ""), "home_id": int(home.get("id") or 0),
                      "away_id": int(away.get("id") or 0), "status": "STATUS_SCHEDULED", "venue": ""}

    def sync_seasons(self, leagues: Optional[List[int]] = None, seasons_back: int = 0, progress=None) -> Dict[str, int]:
        """
        Resultados + calendário. `seasons_back` = quantas temporadas ANTERIORES além da atual (0–5). Temporada passada já
        baixada não é pedida de novo (checkpoint em competition_sync_state).
        """
        from src.data_hub import sync_policy as P
        from src.data_hub.sources.espn import EspnProvider

        say = progress or (lambda msg: None)
        tot = {"partidas": 0, "proximos": 0, "temporadas": 0, "errors": 0, "puladas": 0}
        for lid in leagues or list(LEAGUES):
            try:
                cur = self.league(lid)
            except Exception as exc:
                tot["errors"] += 1
                say(f"  fotmob {lid}: {exc}")
                continue
            seasons = [s for s in (cur.get("allAvailableSeasons") or [])][: 1 + max(0, min(int(seasons_back), 5))]
            for i, season in enumerate(seasons):
                key = f"{lid}:{season}"
                if i > 0 and P.last_synced(self.db, "fotmob", key) is not None:
                    tot["puladas"] += 1                  # temporada encerrada já baixada: não muda mais
                    continue
                try:
                    data = cur if i == 0 else self.league(lid, season)
                except Exception as exc:
                    tot["errors"] += 1
                    say(f"  fotmob {lid} {season}: {exc}")
                    continue
                done, fut = [], []
                for m in (data.get("fixtures") or {}).get("allMatches") or []:
                    try:
                        a, b = self.parse_match(m, lid, season)
                    except Exception:
                        continue
                    if a:
                        done.append(a)
                    if b:
                        fut.append(b)
                if done:
                    self.db.upsert_matches(done)
                if fut and i == 0:
                    EspnProvider.save_fixtures(self, fut)          # mesma tabela `fixtures` da ESPN
                P.mark_synced(self.db, "fotmob", key)
                tot["partidas"] += len(done)
                tot["proximos"] += len(fut) if i == 0 else 0
                tot["temporadas"] += 1
                say(f"  {LEAGUES.get(lid, lid)} {season}: {len(done)} jogos encerrados, {len(fut) if i == 0 else 0} próximos")
        return tot

    # ------------------------------------------------------------------ jogo
    @staticmethod
    def parse_details(d: Dict[str, Any], internal_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
        """(caixa de estatísticas no formato do laboratório, finalizações, desfalques por time)."""
        c = d.get("content") or {}
        header = d.get("header") or {}
        teams = [t.get("name", "") for t in header.get("teams") or []]
        box: Dict[str, Any] = {"team_stats": [], "lineups": [], "timeline": [], "player_stats": []}
        # estatísticas dos times
        allp = (((c.get("stats") or {}).get("Periods") or {}).get("All") or {}).get("stats") or []
        seen = set()
        for grp in allp:
            for s in grp.get("stats") or []:
                key = STAT_MAP.get(s.get("key"))
                vals = s.get("stats")
                if not key or not isinstance(vals, list) or len(vals) != 2 or len(teams) != 2 or key in seen:
                    continue
                seen.add(key)
                for team, raw in zip(teams, vals):
                    row = stat_row(team, key, raw)
                    if row:
                        box["team_stats"].append(row)
                    pct = re.search(r"\((\d+)%\)", str(raw))
                    if key == "passes_accurate" and pct:
                        box["team_stats"].append(stat_row(team, "pass_accuracy_pct", pct.group(1)))
        # escalação com posição exata
        lu = c.get("lineup") or {}
        unavailable: Dict[str, List[Dict[str, Any]]] = {}
        for side in ("homeTeam", "awayTeam"):
            t = lu.get(side) or {}
            team = t.get("name", "")
            form = t.get("formation") or ""
            coach = (t.get("coach") or {}).get("name", "") if isinstance(t.get("coach"), dict) else ""
            for starter, group in ((1, t.get("starters") or []), (0, t.get("subs") or [])):
                for p in group:
                    role = layout_role(p, form) if starter else None
                    pos = role or ("SUB" if not starter else GENERIC_POS.get(p.get("usualPlayingPositionId"), ""))
                    box["lineups"].append({"team_name": team, "player_name": p.get("name", ""),
                                           "shirt_number": str(p.get("shirtNumber") or ""), "position": pos,
                                           "is_starter": starter, "formation": form, "coach": coach})
                    perf = p.get("performance") or {}
                    for ev in perf.get("events") or []:
                        typ = {"yellowCard": "Yellow Card", "redCard": "Red Card", "yellowRedCard": "Red Card"}.get(ev.get("type"))
                        if typ:
                            box["timeline"].append({"minute": ev.get("time"), "extra_minute": None, "team_name": team,
                                                    "player_name": p.get("name", ""), "related_player": "",
                                                    "event_type": typ, "detail": "fotmob"})
            unavailable[team] = [{"jogador": u.get("name"), "tipo": (u.get("unavailability") or {}).get("type"),
                                  "volta": (u.get("unavailability") or {}).get("expectedReturn")}
                                 for u in t.get("unavailable") or []]
        # números por jogador
        for pid, ps in (c.get("playerStats") or {}).items():
            flat: Dict[str, Any] = {}
            for grp in ps.get("stats") or []:
                for _label, s in (grp.get("stats") or {}).items():
                    st = s.get("stat") or {}
                    k = s.get("key")
                    if not k or st.get("value") is None or k.endswith("_title") or k in DROP_KEYS:
                        continue
                    flat[PLAYER_MAP.get(k, k)] = st.get("value")
                    if st.get("total") is not None:
                        flat[PLAYER_MAP.get(k, k) + "_total"] = st.get("total")
            flat["fotmob_id"] = int(pid) if str(pid).isdigit() else pid      # identidade do atleta (homônimos não se misturam)
            rating = None
            for p in [x for side in ("homeTeam", "awayTeam") for x in ((lu.get(side) or {}).get("starters") or [])
                      + ((lu.get(side) or {}).get("subs") or [])]:
                if str(p.get("id")) == str(pid):
                    rating = (p.get("performance") or {}).get("rating")
            box["player_stats"].append({"team_name": ps.get("teamName", ""), "player_name": ps.get("name", ""),
                                        "position": "GK" if ps.get("isGoalkeeper") else "", "minutes": flat.get("minutes"),
                                        "rating": rating, "stats": flat})
        # gols e substituições
        for ev in ((c.get("matchFacts") or {}).get("events") or {}).get("events") or []:
            typ = ev.get("type")
            team = teams[0] if ev.get("isHome") else teams[1] if len(teams) == 2 else ""
            if typ == "Goal":
                box["timeline"].append({"minute": ev.get("time"), "extra_minute": ev.get("overloadTime") or None,
                                        "team_name": team, "player_name": (ev.get("player") or {}).get("name", "") or ev.get("nameStr", ""),
                                        "related_player": (ev.get("assistInput") or ""), "event_type": "Goal",
                                        "detail": "pênalti" if ev.get("goalDescription") == "Penalty" else ""})
            elif typ == "Substitution":
                sw = ev.get("swap") or []
                if len(sw) == 2:
                    box["timeline"].append({"minute": ev.get("time"), "extra_minute": ev.get("overloadTime") or None,
                                            "team_name": team, "player_name": sw[0].get("name", ""),
                                            "related_player": sw[1].get("name", ""), "event_type": "Substitution",
                                            "detail": "entra / sai"})
        # finalizações (coordenadas FotMob 105×68, convertidas ao padrão 120×80, ataque para a direita)
        shots = []
        id2team = {}
        for t in header.get("teams") or []:
            id2team[t.get("id")] = t.get("name", "")
        for s in ((c.get("shotmap") or {}).get("shots") or []):
            shots.append({"match_id": int(internal_id), "team_name": id2team.get(s.get("teamId"), ""),
                          "player_name": s.get("playerName", ""), "minute": s.get("min"),
                          "x": round(float(s.get("x") or 0) * 120 / 105, 2), "y": round(float(s.get("y") or 0) * 80 / 68, 2),
                          "xg": s.get("expectedGoals"), "xgot": s.get("expectedGoalsOnTarget"),
                          "outcome": s.get("eventType", ""), "situation": s.get("situation", ""),
                          "shot_type": s.get("shotType", ""), "period": s.get("period", ""),
                          "on_target": 1 if s.get("isOnTarget") else 0, "own_goal": 1 if s.get("isOwnGoal") else 0,
                          "source": "fotmob"})
        return box, shots, unavailable

    @staticmethod
    def parse_extras(d: Dict[str, Any]) -> Dict[str, Any]:
        """
        O que a FotMob dá além da súmula: momentum minuto a minuto (+ = mandante pressionando, − = visitante) e por
        onde cada time atacou (esquerda/meio/direita, % por tempo), desfalques com previsão de volta e o craque do jogo.
        """
        c = d.get("content") or {}
        teams = [t.get("name", "") for t in (d.get("header") or {}).get("teams") or []]
        mom = (((c.get("momentum") or {}).get("main") or {}).get("data") or [])
        lu = c.get("lineup") or {}
        unav = {}
        for side in ("homeTeam", "awayTeam"):
            t = lu.get(side) or {}
            unav[t.get("name", "")] = [{"jogador": u.get("name"), "tipo": (u.get("unavailability") or {}).get("type"),
                                       "volta": (u.get("unavailability") or {}).get("expectedReturn")}
                                      for u in t.get("unavailable") or []]
        potm = ((c.get("matchFacts") or {}).get("playerOfTheMatch") or {})
        return {"times": teams, "momentum": [[int(x.get("minute", 0)), float(x.get("value", 0))] for x in mom if isinstance(x, dict)],
                "zonas_ataque": c.get("attackingZones") or {}, "desfalques": unav,
                "craque": {"jogador": (potm.get("name") or {}).get("fullName") if isinstance(potm.get("name"), dict) else potm.get("name"),
                           "nota": (potm.get("rating") or {}).get("num") if isinstance(potm.get("rating"), dict) else None}
                if potm else None}

    def extras(self, internal_id: int, fetch: bool = True) -> Dict[str, Any]:
        """Momentum, zonas de ataque e desfalques do jogo; jogos baixados antes da rodada 5 buscam só isso na hora."""
        import json as _json

        self.ensure_tables()
        with self.db.connect() as conn:
            r = conn.execute("SELECT extra_json FROM match_extra WHERE match_id = ?", (int(internal_id),)).fetchone()
        if r:
            return _json.loads(r[0] or "{}")
        if not fetch or not self.enabled:
            return {}
        fid = int(internal_id) - to_internal_id("fotmob", 0)
        d = self._get("matchDetails", {"matchId": fid}, max_age_s=None, cache=False)
        ex = self.parse_extras(d)
        _box, shots, _u = self.parse_details(d, internal_id)
        with self.db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO match_extra VALUES (?, 'fotmob', ?)",
                         (int(internal_id), _json.dumps(ex, ensure_ascii=False, separators=(",", ":"))))
            if shots and not conn.execute("SELECT 1 FROM match_shots WHERE match_id = ? LIMIT 1", (int(internal_id),)).fetchone():
                cols = list(shots[0].keys())
                conn.executemany(f"INSERT INTO match_shots ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                                 [tuple(s[k] for k in cols) for s in shots])
        return ex

    def ensure_tables(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(SHOTS_DDL)
            conn.execute("CREATE TABLE IF NOT EXISTS match_extra (match_id INTEGER PRIMARY KEY, source TEXT, extra_json TEXT)")

    def ingest(self, internal_id: int) -> Dict[str, Any]:
        """Baixa e grava os detalhes de UM jogo (sob demanda ou em lote). Jogo encerrado e consolidado é congelado."""
        from src.data_hub import sync_policy as P

        if P.is_frozen(self.db, internal_id) and self.db.has_boxscore(int(internal_id)):
            return {"match_id": internal_id, "ja_tinha": True}
        fid = int(internal_id) - to_internal_id("fotmob", 0)
        d = self._get("matchDetails", {"matchId": fid}, max_age_s=None, cache=False)   # sem cache bruto: guarda só o que usa
        box, shots, unav = self.parse_details(d, internal_id)
        self.db.save_boxscore(int(internal_id), box)
        self.ensure_tables()
        with self.db.connect() as conn:
            conn.execute("DELETE FROM match_shots WHERE match_id = ?", (int(internal_id),))
            if shots:
                cols = list(shots[0].keys())
                conn.executemany(f"INSERT INTO match_shots ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                                 [tuple(s[k] for k in cols) for s in shots])
            try:
                import json as _json

                conn.execute("INSERT OR REPLACE INTO match_extra VALUES (?, 'fotmob', ?)",
                             (int(internal_id), _json.dumps(self.parse_extras(d), ensure_ascii=False, separators=(",", ":"))))
            except Exception:
                pass
            level = DataLevel.BOXSCORE if (box["team_stats"] or box["lineups"]) else DataLevel.RESULT
            conn.execute("UPDATE matches SET data_level = ? WHERE match_id = ?", (level, int(internal_id)))
        if box["team_stats"] or box["lineups"]:
            P.freeze(self.db, [int(internal_id)])
        return {"match_id": internal_id, "estatisticas": len(box["team_stats"]), "escalacao": len(box["lineups"]),
                "finalizacoes": len(shots), "desfalques": unav}

    def fetch_details(self, leagues: Optional[List[int]] = None, since: Optional[str] = None, limit: int = 300,
                      progress=None, stop=None) -> Dict[str, int]:
        """Detalhes dos jogos encerrados que ainda não têm, por prioridade e do mais recente ao mais antigo; retomável."""
        say = progress or (lambda m: None)
        order = leagues or (PRIORITY + [k for k in LEAGUES if k not in PRIORITY])
        since = since or f"{date.today().year - 1}-01-01"
        with self.db.connect() as conn:
            todo = conn.execute(
                "SELECT match_id, json_extract(extra_json, '$.fotmob_league') AS lg, match_date FROM matches "
                "WHERE data_source = 'fotmob' AND home_score IS NOT NULL AND match_date >= ? "
                "AND match_id NOT IN (SELECT DISTINCT match_id FROM match_lineups) "
                "AND match_id NOT IN (SELECT match_id FROM frozen_matches)", (since,)).fetchall() if self._has_frozen() else \
                conn.execute("SELECT match_id, json_extract(extra_json, '$.fotmob_league'), match_date FROM matches "
                             "WHERE data_source = 'fotmob' AND home_score IS NOT NULL AND match_date >= ? "
                             "AND match_id NOT IN (SELECT DISTINCT match_id FROM match_lineups)", (since,)).fetchall()
        rank = {lg: i for i, lg in enumerate(order)}
        tried = self._recently_tried()
        todo = [r for r in todo if r[1] in rank and int(r[0]) not in tried]
        # rodada 14: o mais RECENTE de todas as ligas primeiro (faixas de 120 dias), prioridade dentro da faixa — antes a
        # fila inteira de Brasil/Europa (5 temporadas) vinha antes de qualquer jogo do Paraguai/Uruguai/Chile
        today_n = int(date.today().strftime("%Y%m%d"))

        def _key(r):
            d = int(str(r[2] or "0").replace("-", "")[:8] or 0)
            try:
                age = (date.today() - date(d // 10000, d // 100 % 100, d % 100)).days if d else 9999
            except ValueError:
                age = 9999
            return (age // 120, rank.get(r[1], 999), today_n - d)

        todo.sort(key=_key)
        tot = {"detalhes": 0, "errors": 0, "pendentes": max(len(todo) - limit, 0)}
        t_start = time.time()
        n_run = min(limit, len(todo))
        for i, (mid, _lg, _d) in enumerate(todo[:limit], 1):
            if stop is not None and stop():
                break
            try:
                self.ingest(int(mid))
                tot["detalhes"] += 1
                self._mark_tried(int(mid), True)
            except Exception as exc:
                tot["errors"] += 1
                self._mark_tried(int(mid), False)
                say(f"  fotmob jogo {mid}: {exc}")
            if i % 25 == 0:                       # rodada 16: ritmo e tempo que falta
                el = time.time() - t_start
                rate = i / el if el > 0 else 0
                eta = (n_run - i) / rate if rate > 0 else 0
                say(f"  detalhes: {i}/{n_run} · {rate * 60:.0f} jogos/min · falta ~{eta / 60:.0f} min"
                    + (f" · {tot['errors']} sem dado" if tot["errors"] else ""))
        say(f"  detalhes baixados: {tot['detalhes']} · faltam {tot['pendentes']} (rode de novo para continuar)")
        return tot

    # ------------------------------------------------------------------ tentativas (não repete jogo sem dado)
    def _tried_table(self) -> None:
        with self.db.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS fotmob_tried (match_id INTEGER PRIMARY KEY, tried_at TEXT, ok INTEGER)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fotmob_tried_at ON fotmob_tried(tried_at)")

    def _mark_tried(self, match_id: int, ok: bool) -> None:
        # Uma só conexão por jogo; a tabela/índice também ficam garantidos para chamadas sob demanda.
        with self.db.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS fotmob_tried (match_id INTEGER PRIMARY KEY, tried_at TEXT, ok INTEGER)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fotmob_tried_at ON fotmob_tried(tried_at)")
            conn.execute("INSERT OR REPLACE INTO fotmob_tried VALUES (?, datetime('now'), ?)", (int(match_id), int(ok)))

    def _recently_tried(self, days: int = 7) -> set:
        """Jogos já pedidos que voltaram sem escalação (liga pequena) ou com erro: só tenta de novo depois de 7 dias."""
        self._tried_table()
        with self.db.connect() as conn:
            rows = conn.execute("SELECT match_id FROM fotmob_tried WHERE tried_at >= datetime('now', ?)",
                                (f"-{int(days)} days",)).fetchall()
        return {int(r[0]) for r in rows}

    def pending(self, since: Optional[str] = None) -> int:
        since = since or f"{date.today().year - 5}-01-01"
        with self.db.connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM matches WHERE data_source = 'fotmob' AND home_score IS NOT NULL "
                             "AND match_date >= ? AND match_id NOT IN (SELECT DISTINCT match_id FROM match_lineups)",
                             (since,)).fetchone()[0]
        return max(int(n) - len(self._recently_tried()), 0)

    # ------------------------------------------------------------------ sob demanda (instantâneo)
    def ensure_teams(self, team_names: List[str], n: int = 10, days: int = 400) -> Dict[str, int]:
        """Baixa NA HORA os detalhes dos últimos `n` jogos dos times que ainda não têm (ex.: ao abrir a Escalação)."""
        if not team_names or not self.enabled:
            return {"detalhes": 0}
        ph = ",".join("?" * len(team_names))
        since = (date.today() - __import__("datetime").timedelta(days=days)).isoformat()
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT match_id FROM matches WHERE data_source = 'fotmob' AND home_score IS NOT NULL AND match_date >= ? "
                f"AND (home_team_name IN ({ph}) OR away_team_name IN ({ph})) "
                f"AND match_id NOT IN (SELECT DISTINCT match_id FROM match_lineups) ORDER BY match_date DESC LIMIT ?",
                [since, *team_names, *team_names, int(n)]).fetchall()
        tried = self._recently_tried()
        done = 0
        for (mid,) in rows:
            if int(mid) in tried:
                continue
            try:
                self.ingest(int(mid))
                self._mark_tried(int(mid), True)
                done += 1
            except Exception:
                self._mark_tried(int(mid), False)
        return {"detalhes": done}

    def ensure_match(self, match_id: int, meta: Dict[str, Any]) -> Optional[int]:
        """A mesma partida na FotMob (data ±1 dia + mesmos times), com os detalhes baixados na hora se faltarem."""
        try:
            from src.data_hub.consolidate import siblings

            ids = [int(match_id)] + [int(x["match_id"]) for x in siblings(self.db, int(match_id), meta)]
        except Exception:
            ids = [int(match_id)]
        fm = [m for m in ids if m >= to_internal_id("fotmob", 0)]
        if not fm:
            return None
        mid = fm[0]
        if not self.db.has_boxscore(mid) and mid not in self._recently_tried(1):
            try:
                self.ingest(mid)
                self._mark_tried(mid, True)
            except Exception:
                self._mark_tried(mid, False)
                return None
        return mid

    # ------------------------------------------------------------------ elenco atual (rodada 8)
    ROSTER_DDL = ("CREATE TABLE IF NOT EXISTS fotmob_rosters (team_id INTEGER, team TEXT, player_id INTEGER, name TEXT, "
                  "position TEXT, role TEXT, jersey TEXT, birth TEXT, height INTEGER, country TEXT, injury TEXT, "
                  "market_value REAL, fetched_at TEXT, PRIMARY KEY (team_id, player_id))")

    # rodada 20: tabela nova — a antiga (fotmob_teams) podia guardar o código do time FEMININO para "Cruzeiro"
    # (mesmo nome), e o "elenco atual" vinha com as jogadoras. A nova só aceita jogos do mesmo gênero.
    TEAMS_TABLE = "fotmob_teams_v2"

    def _team_ids_table(self, conn) -> None:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {self.TEAMS_TABLE} (name TEXT PRIMARY KEY, team_id INTEGER)")
        conn.execute(self.ROSTER_DDL)

    def team_id(self, team_names: List[str]) -> Optional[int]:
        """Id do clube na FotMob: guardado, ou lido de um jogo recente dele na FotMob (1 pedido, só na 1ª vez)."""
        names = [n for n in dict.fromkeys(team_names) if n]
        if not names:
            return None
        ph = ",".join("?" * len(names))
        with self.db.connect() as conn:
            self._team_ids_table(conn)
            r = conn.execute(f"SELECT team_id FROM {self.TEAMS_TABLE} WHERE name IN ({ph}) AND team_id IS NOT NULL LIMIT 1",
                             names).fetchone()
            if r:
                return int(r[0])
            from src.data_hub.gender import comp_sql

            rows = conn.execute(f"SELECT match_id FROM matches m WHERE match_id >= ? AND (home_team_name IN ({ph}) OR "
                                f"away_team_name IN ({ph})) AND match_date <= date('now'){comp_sql(names, 'm')} "
                                f"ORDER BY match_date DESC LIMIT 2",
                                [to_internal_id("fotmob", 0), *names, *names]).fetchall()
        from src.data_lake.ids import team_core

        cores = {team_core(n) for n in names}
        for (mid,) in rows:
            try:
                d = self._get("matchDetails", {"matchId": int(mid) - to_internal_id("fotmob", 0)}, max_age_s=None)
            except Exception:
                continue
            g = d.get("general") or {}
            for side in ("homeTeam", "awayTeam"):
                t = g.get(side) or {}
                if t.get("id") and (t.get("name") in names or team_core(t.get("name", "")) in cores):
                    with self.db.connect() as conn:
                        for n in set(names) | {t.get("name")}:
                            conn.execute(f"INSERT OR REPLACE INTO {self.TEAMS_TABLE} VALUES (?, ?)", (n, int(t["id"])))
                    return int(t["id"])
        return None

    @staticmethod
    def parse_squad(d: Dict[str, Any], team_id: int, team: str, fetched_at: str) -> List[Dict[str, Any]]:
        out = []
        groups = (d.get("squad") or {}).get("squad") or []
        for g in groups:
            if (g.get("title") or "") == "coach":
                continue
            for m in g.get("members") or []:
                if not m.get("id") or not m.get("name"):
                    continue
                inj = m.get("injury")
                inj_txt = ""
                if isinstance(inj, dict):
                    inj_txt = str(inj.get("name") or inj.get("expectedReturn") or "lesionado")
                elif inj:
                    inj_txt = "lesionado"
                out.append({"team_id": int(team_id), "team": team, "player_id": int(m["id"]), "name": m["name"],
                            "position": m.get("positionIdsDesc") or ("GK" if g.get("title") == "keepers" else ""),
                            "role": g.get("title") or "",
                            "jersey": str(m.get("shirtNumber") or ""), "birth": m.get("dateOfBirth") or "",
                            "height": m.get("height"), "country": m.get("cname") or "", "injury": inj_txt,
                            "market_value": m.get("transferValue"), "fetched_at": fetched_at})
        return out

    LOANS_DDL = ("CREATE TABLE IF NOT EXISTS fotmob_loans (team_id INTEGER, player_id INTEGER, name TEXT, direction TEXT, "
                 "other_club TEXT, from_date TEXT, to_date TEXT, fetched_at TEXT, PRIMARY KEY (team_id, player_id, direction))")

    @staticmethod
    def parse_loans(d: Dict[str, Any], team_id: int) -> List[Dict[str, Any]]:
        """Empréstimos ATIVOS: 'in' = jogador emprestado AO clube; 'out' = jogador do clube emprestado a outro."""
        data = ((d.get("transfers") or {}).get("data")) or {}
        today = date.today().isoformat()
        out = []
        for key, direction in (("Players in", "in"), ("Players out", "out")):
            for t in data.get(key) or []:
                if not t.get("onLoan") or not t.get("playerId"):
                    continue
                to_date = str(t.get("toDate") or "")[:10]
                if to_date and to_date < today:
                    continue
                out.append({"player_id": int(t["playerId"]), "name": t.get("name") or "", "direction": direction,
                            "other_club": t.get("fromClub") if direction == "in" else t.get("toClub"),
                            "from_date": str(t.get("fromDate") or "")[:10], "to_date": to_date})
        return out

    def loans(self, team_names: List[str]) -> List[Dict[str, Any]]:
        """Empréstimos ativos guardados com o elenco (busca o elenco se ainda não tem)."""
        self.roster(team_names)
        tid = self.team_id(team_names) if self.enabled else None
        if tid is None:
            return []
        with self.db.connect() as conn:
            conn.execute(self.LOANS_DDL)
            cur = conn.execute("SELECT name, direction, other_club, from_date, to_date FROM fotmob_loans WHERE team_id = ?",
                               (tid,))
            return [dict(zip(("name", "direction", "other_club", "from_date", "to_date"), r)) for r in cur.fetchall()]

    def roster(self, team_names: List[str], max_age_h: float = 24, fetch: bool = True) -> List[Dict[str, Any]]:
        """Elenco ATUAL do clube na FotMob (quem está inscrito hoje, com lesões). Guarda por `max_age_h` horas."""
        names = [n for n in dict.fromkeys(team_names) if n]
        if not names:
            return []
        with self.db.connect() as conn:
            self._team_ids_table(conn)
        tid = self.team_id(names) if (fetch and self.enabled) else None
        if tid is None:
            with self.db.connect() as conn:
                ph = ",".join("?" * len(names))
                r = conn.execute(f"SELECT team_id FROM {self.TEAMS_TABLE} WHERE name IN ({ph}) LIMIT 1", names).fetchone()
            tid = int(r[0]) if r and r[0] is not None else None
        if tid is None:
            return []
        with self.db.connect() as conn:
            cur = conn.execute("SELECT * FROM fotmob_rosters WHERE team_id = ?", (tid,))
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, x)) for x in cur.fetchall()]
        fresh = False
        if rows:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(rows[0]["fetched_at"])).total_seconds() / 3600
                fresh = age < max_age_h
            except Exception:
                fresh = False
        if (fresh or not fetch or not self.enabled) and rows:
            return rows
        try:
            d = self._get("teams", {"id": tid}, max_age_s=None, cache=False)
        except Exception:
            return rows
        team = ((d.get("details") or {}).get("name")) or names[0]
        new = self.parse_squad(d, tid, team, now_iso())
        try:                                             # rodada 11: empréstimos ativos (de entrada e de saída)
            loans = self.parse_loans(d, tid)
            with self.db.connect() as conn:
                conn.execute(self.LOANS_DDL)
                conn.execute("DELETE FROM fotmob_loans WHERE team_id = ?", (tid,))
                conn.executemany("INSERT OR REPLACE INTO fotmob_loans VALUES (?,?,?,?,?,?,?,?)",
                                 [(tid, x["player_id"], x["name"], x["direction"], x["other_club"], x["from_date"],
                                   x["to_date"], now_iso()) for x in loans])
        except Exception:
            pass
        if not new:
            return rows
        with self.db.connect() as conn:
            conn.execute("DELETE FROM fotmob_rosters WHERE team_id = ?", (tid,))
            cols = list(new[0].keys())
            conn.executemany(f"INSERT INTO fotmob_rosters ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                             [tuple(r[k] for k in cols) for r in new])
        return new

    def sync_rosters(self, leagues: Optional[List[int]] = None, days: int = 365, progress=None,
                     limit: Optional[int] = None) -> Dict[str, int]:
        """Rodada 20: elenco ATUAL (nascimento, valor de mercado, posição, lesão) de TODOS os clubes das ligas escolhidas
        — Série B/C e sul-americanas não estão no Transfermarkt aberto ("Sem referência" no Scout). ~2 pedidos por clube
        na 1ª vez, 1 depois; elenco com menos de 24 h não é pedido de novo."""
        say = progress or (lambda msg: None)
        lids = leagues or REGIONS["brasil"] + REGIONS["sulamericanas"]
        comps = [LEAGUES[l] for l in lids if l in LEAGUES]
        if not comps:
            return {"clubes": 0, "jogadores": 0}
        since = (date.today() - __import__("datetime").timedelta(days=days)).isoformat()
        ph = ",".join("?" * len(comps))
        with self.db.connect() as conn:
            rows = conn.execute(f"SELECT team, COUNT(*) AS n FROM (SELECT home_team_name AS team FROM matches WHERE "
                                f"data_source='fotmob' AND competition_name IN ({ph}) AND match_date >= ? UNION ALL "
                                f"SELECT away_team_name FROM matches WHERE data_source='fotmob' AND competition_name IN "
                                f"({ph}) AND match_date >= ?) GROUP BY team ORDER BY n DESC",
                                [*comps, since, *comps, since]).fetchall()
        teams = [r[0] for r in rows if r[0]][: limit or None]
        tot = {"clubes": 0, "jogadores": 0, "erros": 0}
        for i, t in enumerate(teams, 1):
            try:
                got = self.roster([t])
                tot["clubes"] += 1 if got else 0
                tot["jogadores"] += len(got or [])
            except Exception:
                tot["erros"] += 1
            if i % 10 == 0 or i == len(teams):
                say(f"  elencos FotMob: {i}/{len(teams)} clubes · {tot['jogadores']} jogadores")
        return tot

    def _has_frozen(self) -> bool:
        try:
            with self.db.connect() as conn:
                conn.execute("SELECT 1 FROM frozen_matches LIMIT 1")
            return True
        except Exception:
            return False


SHOTS_DDL = """
CREATE TABLE IF NOT EXISTS match_shots (
    match_id INTEGER, team_name TEXT, player_name TEXT, minute INTEGER, x REAL, y REAL, xg REAL, xgot REAL,
    outcome TEXT, situation TEXT, shot_type TEXT, period TEXT, on_target INTEGER, own_goal INTEGER, source TEXT
);
CREATE INDEX IF NOT EXISTS idx_shots_match ON match_shots(match_id);
CREATE INDEX IF NOT EXISTS idx_shots_player ON match_shots(player_name);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
