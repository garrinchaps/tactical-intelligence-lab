"""
Understat — xG de equipes, jogadores e de cada finalização (Premier League, La Liga, Bundesliga, Serie A, Ligue 1, RFPL).

O site entrega os dados em JSON (rota /getLeagueData/<liga>/<temporada> e, por partida, /getMatchData/<id>);
versões antigas embutiam o mesmo JSON no HTML (`shotsData = JSON.parse('...')`), lido como reserva.
Coleta educada: cache em disco, temporadas encerradas não são baixadas de novo, 1 requisição a cada 2 s.

Saídas no lake:
* us_partidas   — partidas da temporada com xG de cada lado e o id Understat;
* us_jogadores  — xG, xA, npxG, xGChain, xGBuildup, chutes e passes-chave por jogador na temporada;
* us_finalizacoes — cada chute: minuto, jogador, assistente, situação, resultado, xG e posição (x, y) já
  convertida para o campo StatsBomb (120 × 80) — vira o mapa de finalizações das partidas recentes.
"""

from __future__ import annotations

import codecs
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

BASE = "https://understat.com"
LEAGUES = {"EPL": "Premier League", "La_liga": "La Liga", "Bundesliga": "Bundesliga", "Serie_A": "Serie A",
           "Ligue_1": "Ligue 1", "RFPL": "Russian Premier League"}
CACHE = Path("data/raw/understat")
LICENSE = "Understat.com — dados públicos do site; uso acadêmico com crédito à fonte"
RESULT_PT = {"Goal": "gol", "SavedShot": "defendido", "MissedShots": "para fora", "BlockedShot": "bloqueado",
             "ShotOnPost": "na trave", "OwnGoal": "gol contra"}


def season_start(today: Optional[date] = None) -> int:
    t = today or date.today()
    return t.year if t.month >= 7 else t.year - 1


def _embedded(html: str, var: str) -> Optional[Any]:
    m = re.search(rf"{var}\s*=\s*JSON\.parse\('(.+?)'\)", html, re.S)
    if not m:
        return None
    return json.loads(codecs.decode(m.group(1), "unicode_escape"))


class UnderstatProvider:
    source = "understat"
    enabled = True

    def __init__(self, cache_dir: Path = CACHE, min_interval_s: float = 2.0):
        self.cache = Path(cache_dir)
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def _get(self, path: str, max_age_s: Optional[float]) -> str:
        import requests

        self.cache.mkdir(parents=True, exist_ok=True)
        f = self.cache / (re.sub(r"[^A-Za-z0-9_]+", "_", path.strip("/")) + ".txt")
        if f.exists() and (max_age_s is None or time.time() - f.stat().st_mtime < max_age_s):
            return f.read_text(encoding="utf-8")
        wait = self.min_interval_s - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(f"{BASE}{path}", timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (TacticalIntelligenceLab; uso acadêmico)", "X-Requested-With": "XMLHttpRequest"})
        self._last = time.time()
        r.raise_for_status()
        f.write_text(r.text, encoding="utf-8")
        return r.text

    # --------------------------------------------------------------- liga
    def league_data(self, league: str, season: int) -> Dict[str, Any]:
        cur = season == season_start()
        age = 6 * 3600 if cur else None
        try:
            data = json.loads(self._get(f"/getLeagueData/{league}/{season}", age))
            if isinstance(data, dict) and ("dates" in data or "datesData" in data):
                return {"teams": data.get("teams") or data.get("teamsData") or {},
                        "players": data.get("players") or data.get("playersData") or [],
                        "dates": data.get("dates") or data.get("datesData") or []}
        except Exception:
            pass
        html = self._get(f"/league/{league}/{season}", age)           # formato antigo (JSON embutido)
        return {"teams": _embedded(html, "teamsData") or {}, "players": _embedded(html, "playersData") or [],
                "dates": _embedded(html, "datesData") or []}

    @staticmethod
    def matches_frame(dates: List[Dict[str, Any]], league: str, season: int) -> pd.DataFrame:
        rows = []
        for m in dates:
            if not m.get("isResult"):
                continue
            rows.append({"understat_id": int(m["id"]), "liga": LEAGUES.get(league, league), "temporada": f"{season}/{season + 1}",
                         "data": str(m.get("datetime", ""))[:10], "mandante": m["h"]["title"], "visitante": m["a"]["title"],
                         "mandante_understat_id": m["h"].get("id"), "visitante_understat_id": m["a"].get("id"),
                         "gols_mandante": int(m["goals"]["h"]), "gols_visitante": int(m["goals"]["a"]),
                         "xg_mandante": round(float(m["xG"]["h"]), 3), "xg_visitante": round(float(m["xG"]["a"]), 3)})
        return pd.DataFrame(rows)

    @staticmethod
    def players_frame(players: List[Dict[str, Any]], league: str, season: int) -> pd.DataFrame:
        num = ["games", "time", "goals", "xG", "assists", "xA", "shots", "key_passes", "yellow_cards", "red_cards",
               "npg", "npxG", "xGChain", "xGBuildup"]
        df = pd.DataFrame(players)
        if df.empty:
            return df
        for c in num:
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.rename(columns={"id": "understat_id", "player_name": "nome", "team_title": "clube", "games": "jogos",
                                "time": "minutos", "goals": "gols", "assists": "assistencias", "shots": "chutes",
                                "key_passes": "passes_chave", "position": "posicao", "yellow_cards": "amarelos",
                                "red_cards": "vermelhos"})
        df["liga"], df["temporada"] = LEAGUES.get(league, league), f"{season}/{season + 1}"
        return df

    # ------------------------------------------------------------ partida
    def match_shots(self, match_id: int) -> List[Dict[str, Any]]:
        try:
            data = json.loads(self._get(f"/getMatchData/{int(match_id)}", None))
            shots = data.get("shots") or data.get("shotsData")
            if shots:
                return list(shots.get("h", [])) + list(shots.get("a", []))
        except Exception:
            pass
        html = self._get(f"/match/{int(match_id)}", None)
        s = _embedded(html, "shotsData") or {}
        return list(s.get("h", [])) + list(s.get("a", []))

    @staticmethod
    def shots_frame(shots: List[Dict[str, Any]]) -> pd.DataFrame:
        rows = []
        for s in shots:
            x, y = float(s["X"]), float(s["Y"])
            rows.append({"understat_id": int(s["match_id"]), "minuto": int(s["minute"]), "lado": s["h_a"],
                         "equipe": s["h_team"] if s["h_a"] == "h" else s["a_team"], "jogador": s["player"],
                         "understat_jogador_id": s.get("player_id"), "assistente": s.get("player_assisted"),
                         "situacao": s.get("situation"), "tipo": s.get("shotType"), "ultima_acao": s.get("lastAction"),
                         "resultado": RESULT_PT.get(s.get("result"), s.get("result")), "xg": round(float(s["xG"]), 4),
                         # Understat: X = 0..1 no comprimento rumo ao gol atacado; Y = 0..1 na largura (de cima p/ baixo)
                         "x": round(120 * x, 2), "y": round(80 * y, 2), "data": str(s.get("date", ""))[:10]})
        return pd.DataFrame(rows)

    # --------------------------------------------------------------- sync
    def sync(self, lake, seasons_back: int = 0, leagues: Optional[List[str]] = None, max_matches_shots: int = 120,
             progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        prov = dict(source="Understat", connector="UnderstatProvider", license=LICENSE)
        cur = season_start()
        tot = {"partidas": 0, "jogadores": 0, "finalizacoes": 0, "errors": 0}
        for lg in leagues or list(LEAGUES):
            for y in range(cur - seasons_back, cur + 1):
                try:
                    d = self.league_data(lg, y)
                except Exception as exc:
                    tot["errors"] += 1
                    say(f"  understat {lg} {y}: {exc}")
                    continue
                m, p = self.matches_frame(d["dates"], lg, y), self.players_frame(d["players"], lg, y)
                if not m.empty:
                    lake.upsert("us_partidas", m, ["understat_id"], **prov)
                    tot["partidas"] += len(m)
                if not p.empty:
                    lake.upsert("us_jogadores", p, ["understat_id", "temporada", "clube"], **prov)
                    tot["jogadores"] += len(p)
                say(f"  understat {LEAGUES.get(lg, lg)} {y}/{y + 1}: {len(m)} partidas, {len(p)} jogadores")
        # finalizações: só das partidas recentes que ainda não foram baixadas (cache permanente por partida)
        have = set(lake.read("us_finalizacoes", ["understat_id"])["understat_id"]) if lake.exists("us_finalizacoes") else set()
        allm = lake.read("us_partidas") if lake.exists("us_partidas") else pd.DataFrame()
        todo = allm[~allm["understat_id"].isin(have)].sort_values("data", ascending=False).head(max_matches_shots) \
            if not allm.empty else allm
        parts = []
        for mid in todo["understat_id"].tolist() if not todo.empty else []:
            try:
                parts.append(self.shots_frame(self.match_shots(int(mid))))
            except Exception as exc:
                tot["errors"] += 1
                say(f"  understat partida {mid}: {exc}")
        if parts:
            sf = pd.concat(parts, ignore_index=True)
            lake.upsert("us_finalizacoes", sf, ["understat_id", "minuto", "jogador", "xg"], **prov)
            tot["finalizacoes"] += len(sf)
        tot["updated"] = tot["partidas"]
        return tot
