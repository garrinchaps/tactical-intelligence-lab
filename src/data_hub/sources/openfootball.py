"""
openfootball / football.json (github.com/openfootball/football.json) — domínio público (CC0 1.0).

Resultados de dezenas de ligas e copas (Inglaterra das 4 divisões, Alemanha, Espanha, Itália, França, Portugal,
Holanda, Bélgica, Áustria, Suíça, Turquia, Grécia, Escócia, Brasil, Argentina, México, MLS, Japão, China,
Champions/Europa League…) desde 2010. Os arquivos "-full" trazem também autores e minutos dos gols, pênaltis,
gols contra, escalações, substituições, cartões, estádio, público e árbitro → partidas com esses detalhes entram no
nível BOXSCORE (placar + linha do tempo + escalações); as demais, no nível RESULT.

Atualização: `git pull` numa cópia local (data/raw/openfootball/football.json) quando o git está instalado; senão
baixa o .zip do repositório. Uma vez por dia na sincronização automática.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.data_hub.registry import DataLevel, to_internal_id

REPO = "https://github.com/openfootball/football.json"
ZIP = "https://codeload.github.com/openfootball/football.json/zip/refs/heads/master"
LOCAL = Path("data/raw/openfootball/football.json")
LICENSE = "openfootball/football.json — CC0 1.0 (domínio público)"
COUNTRY = {"en": "England", "de": "Germany", "es": "Spain", "it": "Italy", "fr": "France", "pt": "Portugal",
           "nl": "Netherlands", "be": "Belgium", "at": "Austria", "ch": "Switzerland", "tr": "Turkey", "gr": "Greece",
           "sco": "Scotland", "br": "Brazil", "ar": "Argentina", "mx": "Mexico", "mls": "USA", "jp": "Japan",
           "cn": "China", "ru": "Russia", "cz": "Czech Republic", "hu": "Hungary", "au": "Australia", "ma": "Morocco",
           "dz": "Algeria", "eg": "Egypt", "co": "Colombia", "uefa": "Europe", "copa": "South America"}


def _sid(*parts: Any) -> int:
    return int(hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:12], 16) % 90_000_000


def nice_name(n: str) -> str:
    """'MOHAMED SALAH' → 'Mohamed Salah'; 'Virgil VAN DIJK' → 'Virgil Van Dijk' (o arquivo grafa sobrenomes em caixa alta)."""
    return " ".join(t.capitalize() if t.isupper() and len(t) > 1 else t for t in str(n).split())


def minute(m: Any) -> Tuple[Optional[int], Optional[int]]:
    s = str(m or "").replace("'", "").strip()
    mm = re.match(r"(\d+)(?:\+(\d+))?", s)
    return (int(mm.group(1)), int(mm.group(2)) if mm.group(2) else None) if mm else (None, None)


def split_name(file_name: str) -> Tuple[str, str]:
    """'England | Premier League 2025/26' → ('Premier League', '2025/26'); 'Brasileiro Série A 2026' → (…, '2026')."""
    n = file_name.split("|")[-1].strip()
    m = re.search(r"\s(\d{4}(?:/\d{2,4})?)$", n)
    return (n[: m.start()].strip(), m.group(1)) if m else (n, "")


class OpenFootballProvider:
    source = "openfootball"
    enabled = True

    def __init__(self, db, local: Path = LOCAL):
        self.db = db
        self.local = Path(local)

    # ------------------------------------------------------------ cópia local
    def update_local(self, say: Callable[[str], None] = lambda m: None) -> str:
        git = shutil.which("git")
        if git:
            try:
                if (self.local / ".git").exists():
                    subprocess.run([git, "-C", str(self.local), "pull", "--ff-only", "-q"], check=True, timeout=600)
                    return "git pull"
                self.local.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run([git, "clone", "-q", "--depth", "1", REPO, str(self.local)], check=True, timeout=900)
                return "git clone"
            except Exception as exc:
                say(f"  openfootball: git falhou ({exc}); tentando o .zip")
        import requests

        r = requests.get(ZIP, timeout=300)
        r.raise_for_status()
        tmp = self.local.parent / "_zip"
        shutil.rmtree(tmp, ignore_errors=True)
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(tmp)
        inner = next(tmp.iterdir())
        shutil.rmtree(self.local, ignore_errors=True)
        shutil.move(str(inner), str(self.local))
        shutil.rmtree(tmp, ignore_errors=True)
        return "zip"

    # ----------------------------------------------------------------- parsing
    @staticmethod
    def files(root: Path) -> List[Path]:
        """Um arquivo por liga/temporada, preferindo a versão '-full' (com gols e escalações)."""
        out: Dict[Tuple[str, str], Path] = {}
        for f in sorted(root.glob("*/*.json")):
            key = (f.parent.name, f.name.replace("-full", ""))
            if key not in out or "-full" in f.name:
                out[key] = f
        return list(out.values())

    @classmethod
    def parse_file(cls, path: Path) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        comp, season = split_name(data.get("name", path.stem))
        code = path.name.split(".")[0]
        season = season or path.parent.name.replace("-", "/")
        out = []
        for m in data.get("matches", []):
            ft = (m.get("score") or {}).get("ft")
            if not ft or len(ft) != 2:
                continue                                       # ainda não jogada
            home, away = m["team1"], m["team2"]
            sid = _sid(path.parent.name, path.name.replace("-full", ""), m.get("date"), home, away)
            rec = {"match_id": to_internal_id("openfootball", sid), "source_match_id": f"{path.parent.name}/{path.name}:{m.get('date')}:{home}:{away}",
                   "competition_name": comp, "season_name": season, "country_name": COUNTRY.get(code, code.upper()),
                   "round_name": m.get("round", ""), "match_date": m.get("date", ""), "home_team_name": home,
                   "away_team_name": away, "home_score": int(ft[0]), "away_score": int(ft[1]),
                   "stadium_name": m.get("ground", ""),
                   "referee_name": ((m.get("referees") or [{}])[0] or {}).get("name", ""),
                   "status": "FT", "data_source": "openfootball", "data_level": DataLevel.RESULT,
                   "extra": {"publico": m.get("attendance"), "intervalo": (m.get("score") or {}).get("ht")}}
            timeline, lineups = [], []
            for side, team in (("goals1", home), ("goals2", away)):
                for g in m.get(side) or []:
                    mi, ex = minute(g.get("minute"))
                    detail = "Own Goal" if g.get("owngoal") else ("Penalty" if g.get("penalty") else "Normal Goal")
                    timeline.append({"minute": mi, "extra_minute": ex, "team_name": team, "player_name": nice_name(g.get("name", "")),
                                     "related_player": None, "event_type": "Goal", "detail": detail})
            for idx, team in enumerate((home, away)):
                for b in ((m.get("bookings") or [[], []])[idx] if len(m.get("bookings") or []) > idx else []):
                    mi, ex = minute(b.get("minute"))
                    timeline.append({"minute": mi, "extra_minute": ex, "team_name": team, "player_name": nice_name(b.get("name", "")),
                                     "related_player": None, "event_type": "Card",
                                     "detail": {"Y": "Yellow Card", "R": "Red Card", "Y/R": "Second Yellow"}.get(b.get("type"), b.get("type"))})
                lu = (m.get("lineup") or [])
                if len(lu) > idx:
                    for p in lu[idx].get("starter") or []:
                        lineups.append({"team_name": team, "player_name": nice_name(p["name"]), "is_starter": 1})
                    for p in lu[idx].get("bench") or []:
                        lineups.append({"team_name": team, "player_name": nice_name(p["name"]), "is_starter": 0})
                    for s in lu[idx].get("subs") or []:
                        mi, ex = minute(s.get("minute"))
                        timeline.append({"minute": mi, "extra_minute": ex, "team_name": team, "player_name": nice_name(s.get("on", "")),
                                         "related_player": nice_name(s.get("off", "")), "event_type": "subst", "detail": "Substitution"})
            if timeline or lineups:
                rec["data_level"] = DataLevel.BOXSCORE
            out.append((rec, {"team_stats": [], "lineups": lineups, "timeline": sorted(timeline, key=lambda e: (e["minute"] or 0, e["extra_minute"] or 0))}))
        return out

    # --------------------------------------------------------------------- sync
    def sync(self, update: bool = True, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        if update:
            say(f"  openfootball: cópia local atualizada por {self.update_local(say)}")
        tot = {"added": 0, "updated": 0, "files": 0, "boxscores": 0}
        for f in self.files(self.local):
            try:
                rows = self.parse_file(f)
            except Exception as exc:
                say(f"  openfootball {f.parent.name}/{f.name}: {exc}")
                continue
            if not rows:
                continue
            r = self.db.upsert_matches([rec for rec, _ in rows])
            for rec, box in rows:
                if box["timeline"] or box["lineups"]:
                    self.db.save_boxscore(rec["match_id"], box)
                    tot["boxscores"] += 1
            tot["added"] += r["added"]
            tot["updated"] += r["updated"]
            tot["files"] += 1
        say(f"  openfootball: {tot['files']} arquivos, {tot['added']} partidas novas, {tot['boxscores']} com gols/escalações")
        return tot
