"""
open-matchday (github.com/oladeeayo/open-matchday) — temporada 2026/27 em dezenas de competições, reconstruída
todo dia a partir de OpenLigaDB, fixturedownload, ESPN e football-data.co.uk.

Por competição (pasta `<PAÍS>_<NÍVEL>_<slug>`, ex.: ENG_1_premier-league):
  results_2627.csv   gw, date, time, home, away, ft_home, ft_away, ft_result, ht_home, ht_away, ht_result,
                     home_shots … away_red (quando o football-data.co.uk tem o jogo), goal_minutes, source
  fixtures_2627.csv  gw, date, time, home, away            → agenda (próximos jogos)
  goals_2627.csv     gw, date, home, away, minute, score_home, score_away, scorer

O que acrescenta ao app: resultados da temporada atual em ligas que outras fontes demoram a publicar, placar do
intervalo, minuto (e às vezes autor) dos gols e a agenda. As estatísticas são as do football-data.co.uk (mesmos
números da fonte fdcouk, por isso entram como "mesma partida em outra fonte", sem duplicar).
Termos do projeto: dados informativos, uso não comercial, sem revenda.
"""

from __future__ import annotations

import io
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.data_hub.registry import DataLevel, to_internal_id
from src.data_hub.tabular import find_col, normalize_columns, parse_date, parse_minute, stable_id, stat, to_int

BASE = "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data"
CACHE = Path("data/raw/open_matchday")
LICENSE = "open-matchday — informativo, uso não comercial; os dados pertencem aos provedores originais"
COMPETITIONS: Dict[str, Tuple[str, str]] = {   # pasta → (nome, país); pastas inexistentes são só puladas
    "ENG_1_premier-league": ("Premier League", "England"), "ENG_2_championship": ("Championship", "England"),
    "ENG_3_league-one": ("League One", "England"), "ENG_4_league-two": ("League Two", "England"),
    "ESP_1_la-liga": ("La Liga", "Spain"), "ESP_2_segunda-division": ("La Liga 2", "Spain"),
    "ITA_1_serie-a": ("Serie A", "Italy"), "ITA_2_serie-b": ("Serie B", "Italy"),
    "GER_1_bundesliga": ("Bundesliga", "Germany"), "GER_2_2-bundesliga": ("2. Bundesliga", "Germany"),
    "GER_3_3-liga": ("3. Liga", "Germany"), "FRA_1_ligue-1": ("Ligue 1", "France"), "FRA_2_ligue-2": ("Ligue 2", "France"),
    "NED_1_eredivisie": ("Eredivisie", "Netherlands"), "POR_1_primeira-liga": ("Primeira Liga", "Portugal"),
    "BEL_1_pro-league": ("Jupiler Pro League", "Belgium"), "TUR_1_super-lig": ("Süper Lig", "Turkey"),
    "GRE_1_super-league": ("Super League Greece", "Greece"), "SCO_1_premiership": ("Scottish Premiership", "Scotland"),
    "SCO_2_championship": ("Scottish Championship", "Scotland"), "SCO_3_league-one": ("Scottish League One", "Scotland"),
    "UEFA_1_champions-league": ("UEFA Champions League", "Europe"), "UEFA_2_europa-league": ("UEFA Europa League", "Europe"),
    "BRA_1_serie-a": ("Campeonato Brasileiro Série A", "Brazil"), "BRA_2_serie-b": ("Campeonato Brasileiro Série B", "Brazil"),
    "ARG_1_primera-division": ("Liga Profesional", "Argentina"),
    "CONMEBOL_1_copa-libertadores": ("CONMEBOL Libertadores", "South America"),
}
# home_<x> / away_<x> → chave padrão
STAT_KEYS = [("shots_on_target", "shots_on_target", "Finalizações no gol"), ("sot", "shots_on_target", "Finalizações no gol"),
             ("shots", "shots_total", "Finalizações"), ("corners", "corners", "Escanteios"),
             ("fouls", "fouls", "Faltas cometidas"), ("yellow", "yellow_cards", "Cartões amarelos"),
             ("red", "red_cards", "Cartões vermelhos")]


def season_code(today: Optional[date] = None) -> str:
    t = today or date.today()
    y = t.year if t.month >= 7 else t.year - 1
    return f"{y % 100:02d}{(y + 1) % 100:02d}"


class OpenMatchdayProvider:
    source = "open_matchday"

    def __init__(self, db=None, fetch: Optional[Callable[[str], bytes]] = None):
        self.db = db
        self._fetch = fetch

    def _csv(self, folder: str, kind: str, season: str, max_age_h: float = 12) -> pd.DataFrame:
        CACHE.mkdir(parents=True, exist_ok=True)
        cached = CACHE / f"{folder}_{kind}_{season}.csv"
        if cached.exists() and (time.time() - cached.stat().st_mtime) < max_age_h * 3600:
            data = cached.read_bytes()
        else:
            url = f"{BASE}/{folder}/{kind}_{season}.csv"
            try:
                if self._fetch is not None:
                    data = self._fetch(url)
                else:
                    from src.data_hub import net

                    r = net.get(url, source="open_matchday", retries=2)
                    if r.status_code == 404:
                        return pd.DataFrame()
                    r.raise_for_status()
                    data = r.content
            except Exception:
                if not cached.exists():
                    raise
                data = cached.read_bytes()
            cached.write_bytes(data)
        if not data or not data.strip():
            return pd.DataFrame()
        return normalize_columns(pd.read_csv(io.BytesIO(data), on_bad_lines="skip"))

    @staticmethod
    def match_id(folder: str, d: str, home: str, away: str) -> int:
        return to_internal_id("open_matchday", stable_id(folder, d, home.lower(), away.lower()))

    @classmethod
    def parse_results(cls, df: pd.DataFrame, folder: str, season: str,
                      goals: Optional[pd.DataFrame] = None) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        name, country = COMPETITIONS.get(folder, (folder, ""))
        if df.empty:
            return []
        c_d, c_h, c_a = find_col(df, "date"), find_col(df, "home"), find_col(df, "away")
        c_fh, c_fa = find_col(df, "ft_home", "fthg"), find_col(df, "ft_away", "ftag")
        c_hh, c_ha = find_col(df, "ht_home", "hthg"), find_col(df, "ht_away", "htag")
        c_gw, c_gm = find_col(df, "gw", "round"), find_col(df, "goal_minutes")
        stat_cols: List[Tuple[str, str, str, str]] = []      # (col_home, col_away, key, label)
        used = set()
        for suf, key, lab in STAT_KEYS:
            ch = next((c for c in df.columns if c.startswith("home_") and c[5:] == suf and c not in used), None) or \
                 next((c for c in df.columns if c.startswith("home_") and suf in c[5:] and c not in used), None)
            if not ch:
                continue
            ca = "away_" + ch[5:]
            if ca in df.columns and key not in {k for _, _, k, _ in stat_cols}:
                stat_cols.append((ch, ca, key, lab))
                used |= {ch, ca}
        gl: Dict[Tuple[str, str, str], List[Dict]] = {}
        if goals is not None and not goals.empty:
            g_d, g_h, g_a = find_col(goals, "date"), find_col(goals, "home"), find_col(goals, "away")
            g_m, g_sh, g_sa = find_col(goals, "minute"), find_col(goals, "score_home"), find_col(goals, "score_away")
            g_s = find_col(goals, "scorer")
            for r in goals.to_dict("records"):
                gl.setdefault((parse_date(r.get(g_d)), str(r.get(g_h)), str(r.get(g_a))), []).append(r)
        out = []
        for r in df.to_dict("records"):
            d, h, a = parse_date(r.get(c_d)), str(r.get(c_h) or "").strip(), str(r.get(c_a) or "").strip()
            hs, as_ = to_int(r.get(c_fh)), to_int(r.get(c_fa))
            if not d or not h or not a or hs is None or as_ is None:
                continue
            stats = [s for ch, ca, key, lab in stat_cols
                     for s in (stat(h, key, lab, r.get(ch)), stat(a, key, lab, r.get(ca))) if s]
            hh, ha = (to_int(r.get(c_hh)), to_int(r.get(c_ha))) if c_hh and c_ha else (None, None)
            if hh is not None and ha is not None:
                stats += [s for s in (stat(h, "ht_goals", "Gols no 1º tempo", hh), stat(a, "ht_goals", "Gols no 1º tempo", ha)) if s]
            timeline = cls._timeline(gl.get((d, h, a), []), h, a, goals) or cls._minutes(r.get(c_gm) if c_gm else None)
            has_stats = any(s["stat_key"] != "ht_goals" for s in stats)
            rec = {"match_id": cls.match_id(folder, d, h, a), "home_team_name": h, "away_team_name": a, "match_date": d,
                   "home_score": hs, "away_score": as_, "competition_name": name, "season_name": f"20{season[:2]}/20{season[2:]}",
                   "country_name": country, "status": "FT", "round_name": f"Rodada {to_int(r.get(c_gw))}" if c_gw and
                   to_int(r.get(c_gw)) else "", "data_source": "open_matchday",
                   "data_level": DataLevel.BOXSCORE if has_stats else DataLevel.RESULT}
            out.append((rec, {"team_stats": stats, "lineups": [], "timeline": timeline}))
        return out

    @staticmethod
    def _timeline(rows: List[Dict], home: str, away: str, goals: Optional[pd.DataFrame]) -> List[Dict]:
        if not rows:
            return []
        g_m, g_sh, g_sa = find_col(goals, "minute"), find_col(goals, "score_home"), find_col(goals, "score_away")
        g_s = find_col(goals, "scorer")
        out, prev = [], (0, 0)
        for r in sorted(rows, key=lambda x: parse_minute(x.get(g_m)) or 0):
            sh, sa = to_int(r.get(g_sh)), to_int(r.get(g_sa))
            team = home if (sh is not None and sh > prev[0]) else (away if (sa is not None and sa > prev[1]) else "")
            prev = (sh if sh is not None else prev[0], sa if sa is not None else prev[1])
            out.append({"minute": parse_minute(r.get(g_m)), "extra_minute": None, "team_name": team,
                        "player_name": str(r.get(g_s) or "") if g_s and pd.notna(r.get(g_s)) else "",
                        "related_player": "", "event_type": "Goal", "detail": "Normal Goal"})
        return out

    @staticmethod
    def _minutes(v: Any) -> List[Dict]:
        """goal_minutes sem autor (ex.: '12,45+1,78'): vira linha do tempo só com o minuto."""
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return []
        return [{"minute": parse_minute(m), "extra_minute": None, "team_name": "", "player_name": "", "related_player": "",
                 "event_type": "Goal", "detail": "Normal Goal"} for m in re.split(r"[;,|]", str(v)) if parse_minute(m) is not None]

    @staticmethod
    def parse_fixtures(df: pd.DataFrame, folder: str) -> pd.DataFrame:
        name, country = COMPETITIONS.get(folder, (folder, ""))
        if df.empty:
            return pd.DataFrame()
        c_d, c_t, c_h, c_a = find_col(df, "date"), find_col(df, "time"), find_col(df, "home"), find_col(df, "away")
        out = pd.DataFrame({"data": df[c_d].map(parse_date), "hora": df[c_t].astype(str) if c_t else "",
                            "mandante": df[c_h].astype(str), "visitante": df[c_a].astype(str)})
        out["competicao"], out["pais"], out["fonte"] = name, country, "open_matchday"
        return out[out["data"] != ""]

    def sync(self, lake=None, folders: Optional[List[str]] = None, progress: Optional[Callable[[str], None]] = None
             ) -> Dict[str, int]:
        say = progress or (lambda m: None)
        season = season_code()
        tot = {"added": 0, "updated": 0, "errors": 0, "competicoes": 0, "agenda": 0}
        fixtures = []
        for folder in folders or COMPETITIONS:
            try:
                res = self._csv(folder, "results", season)
                if res.empty:
                    continue
                try:
                    goals = self._csv(folder, "goals", season)
                except Exception:
                    goals = pd.DataFrame()
                rows = self.parse_results(res, folder, season, goals)
                r = self.db.upsert_matches([rec for rec, _ in rows])
                for rec, box in rows:
                    if box["team_stats"] or box["timeline"]:
                        if not self.db.has_boxscore(rec["match_id"]) or box["team_stats"]:
                            self.db.save_boxscore(rec["match_id"], box)
                tot["added"] += r["added"]
                tot["updated"] += r["updated"]
                tot["competicoes"] += 1
                try:
                    fx = self.parse_fixtures(self._csv(folder, "fixtures", season), folder)
                    if not fx.empty:
                        fixtures.append(fx)
                except Exception:
                    pass
                say(f"  open-matchday {COMPETITIONS.get(folder, (folder,))[0]}: {len(rows)} jogos")
            except Exception as exc:
                tot["errors"] += 1
                say(f"  open-matchday {folder}: {exc}")
        if fixtures and lake is not None:
            fx = pd.concat(fixtures, ignore_index=True)
            fx = fx[fx["data"] >= date.today().isoformat()]
            lake.write("agenda", fx, source="open-matchday", connector="OpenMatchdayProvider", license=LICENSE)
            tot["agenda"] = len(fx)
        return tot
