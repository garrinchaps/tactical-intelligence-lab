"""
Ingestor de fontes abertas (config/open_sources.yaml).

Baixa cada arquivo da lista (CSV/JSON publicados para download livre), guarda no lake como `os_<id>` com hash por
linha (sem duplicar entre execuções) e, quando a fonte declara `catalogo`, converte em partidas do catálogo do app.
Uma requisição por arquivo, com cache por ETag; nenhuma varredura de sites.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

CONFIG = Path("config/open_sources.yaml")
CACHE = Path("data/raw/open_sources")


def load_config(path: Path = CONFIG) -> List[Dict[str, Any]]:
    try:
        import yaml  # type: ignore

        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        from src.connectors.mini_yaml import safe_load

        doc = safe_load(path.read_text(encoding="utf-8"))
    items = (doc or {}).get("fontes") or []
    for i, f in enumerate(items):
        for k in ("id", "url", "formato", "licenca"):
            if not f.get(k):
                raise ValueError(f"{path}, fonte {i + 1}: campo '{k}' obrigatório")
    return items


def _row_hash(df: pd.DataFrame) -> pd.Series:
    return "h" + pd.util.hash_pandas_object(df.astype(str), index=False).astype(str)


class OpenSourcesIngestor:
    source = "open_sources"
    enabled = True

    def __init__(self, config: Path = CONFIG, cache: Path = CACHE, fetch: Optional[Callable[[str, Dict[str, str]], Any]] = None):
        self.config, self.cache = Path(config), Path(cache)
        self._fetch = fetch

    def _download(self, src: Dict[str, Any]) -> bytes:
        self.cache.mkdir(parents=True, exist_ok=True)
        f, meta = self.cache / f"{src['id']}.bin", self.cache / f"{src['id']}.meta.json"
        if f.exists() and time.time() - f.stat().st_mtime < 20 * 3600:
            return f.read_bytes()
        headers = {"User-Agent": "TacticalIntelligenceLab/1.0 (pesquisa academica)"}
        if meta.exists() and f.exists():
            etag = json.loads(meta.read_text()).get("etag")
            if etag:
                headers["If-None-Match"] = etag
        if self._fetch:
            status, body, etag = self._fetch(src["url"], headers)
        else:
            import requests

            r = requests.get(src["url"], headers=headers, timeout=120)
            status, body, etag = r.status_code, r.content, r.headers.get("ETag")
        if status == 304 and f.exists():
            f.touch()
            return f.read_bytes()
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        f.write_bytes(body)
        meta.write_text(json.dumps({"etag": etag}))
        return body

    @staticmethod
    def parse(src: Dict[str, Any], body: bytes) -> pd.DataFrame:
        if src["formato"] == "json":
            data = json.loads(body.decode("utf-8-sig"))
            rec = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [data])
            return pd.json_normalize(rec, sep="_")
        return pd.read_csv(io.BytesIO(body), low_memory=False)

    def sync(self, lake, db=None, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        tot = {"fontes": 0, "linhas": 0, "partidas_catalogo": 0, "errors": 0}
        frames: Dict[str, pd.DataFrame] = {}
        for src in load_config(self.config):
            try:
                df = self.parse(src, self._download(src))
            except Exception as exc:
                tot["errors"] += 1
                say(f"  fonte aberta {src['id']}: {exc}")
                continue
            df["row_hash"] = _row_hash(df)
            lake.upsert(f"os_{src['id']}", df, ["row_hash"], source=src.get("nome", src["id"]),
                        connector="OpenSourcesIngestor", license=src["licenca"])
            frames[src["id"]] = df
            tot["fontes"] += 1
            tot["linhas"] += len(df)
            say(f"  fonte aberta {src['id']}: {len(df)} linhas")
            if src.get("catalogo") == "international_results" and db is not None:
                goals = None
                try:
                    goals = self.parse({"formato": "csv"}, self._download(
                        {"id": "intl_gols", "url": src["url"].replace("results.csv", "goalscorers.csv")}))
                except Exception:
                    pass
                tot["partidas_catalogo"] += international_to_catalog(df, goals, db)
        tot["updated"] = tot["linhas"]
        return tot


def international_to_catalog(res: pd.DataFrame, goals: Optional[pd.DataFrame], db) -> int:
    """Jogos de seleções → catálogo (RESULT; BOXSCORE quando há autores dos gols)."""
    from src.data_hub.registry import DataLevel, to_internal_id

    def sid(r) -> int:
        return int(hashlib.sha1(f"{r['date']}|{r['home_team']}|{r['away_team']}".encode()).hexdigest()[:12], 16) % 90_000_000
    res = res.dropna(subset=["home_score", "away_score"]).copy()
    res["mid"] = [to_internal_id("intl", sid(r)) for r in res.to_dict("records")]
    recs = [{"match_id": int(r["mid"]), "source_match_id": f"{r['date']}:{r['home_team']}:{r['away_team']}",
             "competition_name": r["tournament"], "season_name": str(r["date"])[:4], "match_date": r["date"],
             "home_team_name": r["home_team"], "away_team_name": r["away_team"], "home_score": int(r["home_score"]),
             "away_score": int(r["away_score"]), "stadium_name": f"{r.get('city', '')}, {r.get('country', '')}".strip(", "),
             "country_name": r.get("country", ""), "status": "FT", "data_source": "intl", "data_level": DataLevel.RESULT,
             "extra": {"campo_neutro": str(r.get("neutral", "")).upper() == "TRUE", "gender": "male"}}
            for r in res.to_dict("records")]
    boxes: Dict[int, List[Dict[str, Any]]] = {}
    if goals is not None and not goals.empty:
        key = {(r["date"], r["home_team"], r["away_team"]): int(r["mid"]) for r in res.to_dict("records")}
        for g in goals.to_dict("records"):
            mid = key.get((g["date"], g["home_team"], g["away_team"]))
            if mid is None or pd.isna(g.get("minute")):
                continue
            det = "Own Goal" if str(g.get("own_goal")).upper() == "TRUE" else ("Penalty" if str(g.get("penalty")).upper() == "TRUE" else "Normal Goal")
            boxes.setdefault(mid, []).append({"minute": int(float(g["minute"])), "extra_minute": None, "team_name": g["team"],
                                              "player_name": g["scorer"], "related_player": None, "event_type": "Goal", "detail": det})
    for r in recs:
        if r["match_id"] in boxes:
            r["data_level"] = DataLevel.BOXSCORE
    db.upsert_matches(recs)
    for mid, tl in boxes.items():
        db.save_boxscore(mid, {"team_stats": [], "lineups": [], "timeline": tl})
    return len(recs)
