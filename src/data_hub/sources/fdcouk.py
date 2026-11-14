"""
football-data.co.uk — CSVs públicos e gratuitos de resultados e estatísticas de partidas.

* Ligas principais (Inglaterra, Escócia, Alemanha, Itália, Espanha, França, Holanda, Bélgica, Portugal, Turquia,
  Grécia): placar final e do 1º tempo, finalizações, finalizações no alvo, escanteios, faltas e cartões
  → nível BOXSCORE (estatísticas de equipe, sem eventos com coordenadas).
* Ligas extras (Brasil, Argentina, EUA, México, Japão, China e outras): placar → nível RESULT.

O site oferece os arquivos para download livre e pede crédito; o conector baixa um CSV por liga/temporada,
guarda em cache (temporadas encerradas não são baixadas de novo) e respeita um intervalo entre downloads.
"""

from __future__ import annotations

import hashlib
import io
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel, to_internal_id

BASE = "https://www.football-data.co.uk"
CACHE = Path("data/raw/fdcouk")
MAIN_LEAGUES = {
    "E0": ("Premier League", "England"), "E1": ("Championship", "England"), "SC0": ("Scottish Premiership", "Scotland"),
    "D1": ("Bundesliga", "Germany"), "D2": ("2. Bundesliga", "Germany"), "I1": ("Serie A", "Italy"),
    "I2": ("Serie B", "Italy"), "SP1": ("La Liga", "Spain"), "SP2": ("La Liga 2", "Spain"),
    "F1": ("Ligue 1", "France"), "F2": ("Ligue 2", "France"), "N1": ("Eredivisie", "Netherlands"),
    "B1": ("Jupiler Pro League", "Belgium"), "P1": ("Primeira Liga", "Portugal"), "T1": ("Süper Lig", "Turkey"),
    "G1": ("Super League Greece", "Greece"),
}
EXTRA_LEAGUES = {
    "BRA": "Brazil", "ARG": "Argentina", "USA": "USA", "MEX": "Mexico", "JPN": "Japan", "CHN": "China",
    "AUT": "Austria", "DNK": "Denmark", "FIN": "Finland", "IRL": "Ireland", "NOR": "Norway", "POL": "Poland",
    "ROU": "Romania", "RUS": "Russia", "SWE": "Sweden", "SWZ": "Switzerland",
}
# nomes iguais aos usados pelas outras fontes do Data Hub (evita "Serie A" do Brasil confundida com a da Itália)
EXTRA_NAMES = {("BRA", "Serie A"): "Campeonato Brasileiro Série A", ("ARG", "Liga Profesional"): "Liga Profesional",
               ("USA", "MLS"): "Major League Soccer", ("MEX", "Liga MX"): "Liga MX"}
STATS = (  # coluna mandante, coluna visitante, chave, rótulo (mesmos rótulos do restante do Data Hub)
    ("HS", "AS", "shots_total", "Finalizações"), ("HST", "AST", "shots_on_goal", "Finalizações no gol"),
    ("HC", "AC", "corner_kicks", "Escanteios"), ("HF", "AF", "fouls", "Faltas cometidas"),
    ("HY", "AY", "yellow_cards", "Cartões amarelos"), ("HR", "AR", "red_cards", "Cartões vermelhos"),
    ("HTHG", "HTAG", "ht_goals", "Gols no 1º tempo"),
)


def season_code(start_year: int) -> str:
    """2025 → '2526' (formato das pastas mmz4281 do site)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def current_season_start(today: Optional[date] = None) -> int:
    t = today or date.today()
    return t.year if t.month >= 7 else t.year - 1


def _date(s: Any) -> str:
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _sid(*parts: Any) -> int:
    """ID estável por partida (o site não publica IDs): hash de liga, data e equipes."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:12], 16) % 90_000_000


class FootballDataCoUkProvider:
    source = "fdcouk"

    def __init__(self, db: DataHubDB, min_interval_s: float = 2.0, cache_dir: Path = CACHE):
        self.db = db
        self.min_interval_s = min_interval_s
        self.cache_dir = cache_dir
        self._last = 0.0

    enabled = True

    # ------------------------------------------------------------- download
    def _get_csv(self, url: str, max_age_s: Optional[float]) -> pd.DataFrame:
        import requests

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / (url.rsplit("/", 2)[-2] + "_" + url.rsplit("/", 1)[-1])
        if path.exists() and (max_age_s is None or time.time() - path.stat().st_mtime < max_age_s):
            raw = path.read_bytes()
        else:
            wait = self.min_interval_s - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            r = requests.get(url, timeout=30, headers={"User-Agent": "TacticalIntelligenceLab/1.0 (uso acadêmico)"})
            self._last = time.time()
            if r.status_code == 404:
                return pd.DataFrame()
            r.raise_for_status()
            raw = r.content
            path.write_bytes(raw)
        return pd.read_csv(io.BytesIO(raw), encoding="latin-1", on_bad_lines="skip")

    # -------------------------------------------------------------- parsing
    @classmethod
    def parse_main(cls, df: pd.DataFrame, div: str, start_year: int) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        name, country = MAIN_LEAGUES.get(div, (div, ""))
        season = f"{start_year}/{start_year + 1}"
        out = []
        for r in df.dropna(subset=["HomeTeam", "AwayTeam"]).to_dict("records"):
            d = _date(r.get("Date"))
            if not d or pd.isna(r.get("FTHG")):
                continue
            sid = _sid(div, d, r["HomeTeam"], r["AwayTeam"])
            rec = {"match_id": to_internal_id("fdcouk", sid), "source_match_id": f"{div}:{d}:{r['HomeTeam']}:{r['AwayTeam']}",
                   "competition_id": 0, "competition_name": name, "season_id": start_year, "season_name": season,
                   "country_name": country, "match_date": d, "home_team_name": str(r["HomeTeam"]),
                   "away_team_name": str(r["AwayTeam"]), "home_score": int(r["FTHG"]), "away_score": int(r["FTAG"]),
                   "referee_name": str(r.get("Referee") or "") if pd.notna(r.get("Referee")) else "",
                   "status": "FT", "data_source": "fdcouk", "data_level": DataLevel.BOXSCORE}
            stats = []
            for hc, ac, key, label in STATS:
                for col, team in ((hc, r["HomeTeam"]), (ac, r["AwayTeam"])):
                    v = r.get(col)
                    if v is not None and pd.notna(v):
                        stats.append({"team_name": str(team), "stat_key": key, "stat_label": label,
                                      "value": float(v), "display_value": str(int(v))})
            if not stats:
                rec["data_level"] = DataLevel.RESULT
            out.append((rec, {"team_stats": stats}))
        return out

    @classmethod
    def parse_extra(cls, df: pd.DataFrame, code: str) -> List[Dict[str, Any]]:
        out = []
        for r in df.dropna(subset=["Home", "Away"]).to_dict("records"):
            d = _date(r.get("Date"))
            if not d or pd.isna(r.get("HG")):
                continue
            league = str(r.get("League") or code)
            country = str(r.get("Country") or EXTRA_LEAGUES.get(code, ""))
            league = EXTRA_NAMES.get((code, league), f"{league} ({country})" if country else league)
            sid = _sid(code, d, r["Home"], r["Away"])
            season = str(r.get("Season") or d[:4])
            out.append({"match_id": to_internal_id("fdcouk", sid), "source_match_id": f"{code}:{d}:{r['Home']}:{r['Away']}",
                        "competition_id": 0, "competition_name": league, "season_id": int(season[:4]) if season[:4].isdigit() else 0,
                        "season_name": season, "country_name": country,
                        "match_date": d, "home_team_name": str(r["Home"]), "away_team_name": str(r["Away"]),
                        "home_score": int(r["HG"]), "away_score": int(r["AG"]), "status": "FT",
                        "data_source": "fdcouk", "data_level": DataLevel.RESULT})
        return out

    # ----------------------------------------------------------------- sync
    def sync(self, seasons_back: int = 2, leagues: Optional[Iterable[str]] = None,
             extra: Optional[Iterable[str]] = None, progress=None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        tot = {"added": 0, "updated": 0, "errors": 0, "files": 0}
        cur = current_season_start()
        for div in leagues or MAIN_LEAGUES:
            for y in range(cur - seasons_back, cur + 1):
                url = f"{BASE}/mmz4281/{season_code(y)}/{div}.csv"
                try:
                    df = self._get_csv(url, max_age_s=12 * 3600 if y == cur else None)
                except Exception as exc:
                    tot["errors"] += 1
                    say(f"  {div} {y}: {exc}")
                    continue
                if df.empty:
                    continue
                rows = self.parse_main(df, div, y)
                r = self.db.upsert_matches([rec for rec, _ in rows])
                for rec, box in rows:
                    if box["team_stats"]:
                        self.db.save_boxscore(rec["match_id"], box)
                tot["added"] += r["added"]
                tot["updated"] += r["updated"]
                tot["files"] += 1
                say(f"  {MAIN_LEAGUES[div][0]} {y}/{y + 1}: {len(rows)} partidas")
        for code in extra or EXTRA_LEAGUES:
            try:
                df = self._get_csv(f"{BASE}/new/{code}.csv", max_age_s=12 * 3600)
            except Exception as exc:
                tot["errors"] += 1
                say(f"  {code}: {exc}")
                continue
            if df.empty:
                continue
            recs = self.parse_extra(df, code)
            r = self.db.upsert_matches(recs)
            tot["added"] += r["added"]
            tot["updated"] += r["updated"]
            tot["files"] += 1
            say(f"  {code}: {len(recs)} partidas")
        return tot
