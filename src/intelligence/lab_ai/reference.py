"""Régua da base: para cada estatística de time, a distribuição em milhares de jogos (cache em data/processed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

import numpy as np

REF_PATH = Path("data/processed/lab_ai_reference.json")
MAX_GAMES = 6000
MIN_N = 40


def build(db, max_games: int = MAX_GAMES) -> Dict[str, list]:
    """Quantis 0..100 de cada stat_key nos jogos mais recentes com estatísticas (cada time-jogo é uma amostra)."""
    q = ("SELECT s.stat_key, s.value FROM match_team_stats s WHERE s.match_id IN ("
         "SELECT match_id FROM matches WHERE data_level IN ('BOXSCORE','EVENTS') ORDER BY match_date DESC LIMIT ?)")
    with db.connect() as conn:
        rows = conn.execute(q, (int(max_games),)).fetchall()
    by: Dict[str, list] = {}
    for k, v in rows:
        try:
            by.setdefault(str(k), []).append(float(v))
        except (TypeError, ValueError):
            continue
    out = {k: [float(x) for x in np.percentile(np.asarray(v), np.arange(101))] + [len(v)]
           for k, v in by.items() if len(v) >= MIN_N}
    REF_PATH.parent.mkdir(parents=True, exist_ok=True)
    REF_PATH.write_text(json.dumps(out), encoding="utf-8")
    return out


_MEM: Dict[str, object] = {"mtime": None, "ref": {}}


def load(db=None) -> Dict[str, list]:
    if REF_PATH.exists():
        m = REF_PATH.stat().st_mtime
        if m != _MEM["mtime"]:
            _MEM.update(mtime=m, ref=json.loads(REF_PATH.read_text(encoding="utf-8")))
        return _MEM["ref"]  # type: ignore[return-value]
    if db is not None:
        try:
            ref = build(db)
            _MEM.update(mtime=REF_PATH.stat().st_mtime, ref=ref)
            return ref
        except Exception:
            return {}
    return {}


def percentile(ref: Dict[str, list], key: str, value: Optional[float]) -> Optional[float]:
    """Em quantos % dos jogos da base o número foi MENOR que este (0–100). None se não há régua."""
    q = ref.get(key)
    if q is None or value is None:
        return None
    arr = np.asarray(q[:101])
    if arr[-1] <= arr[0]:
        return None
    v = float(value)
    lo, hi = int(np.searchsorted(arr, v, "left")), int(np.searchsorted(arr, v, "right"))
    if hi - lo > 1:                                      # empate (ex.: muitos jogos com 0 vermelhos): meio da faixa
        return float(min(100, max(0, (lo + hi - 1) / 2)))
    return float(np.interp(v, arr, np.arange(101), left=0, right=100))


def sample_size(ref: Dict[str, list], key: str) -> int:
    q = ref.get(key)
    return int(q[101]) if q and len(q) > 101 else 0
