"""Força pré-jogo do adversário por Elo histórico, deduplicando versões da mesma partida."""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from src.data_lake.ids import team_core

_CACHE: Dict[str, Dict[str, Any]] = {}


def _revision(db) -> str:
    raw = getattr(db, "db_path", None)
    if raw is None:
        return f"memory:{id(db)}"
    path = Path(raw).expanduser().resolve()
    stamps = []
    for suffix in ("", "-wal", "-journal"):
        try:
            st = Path(f"{path}{suffix}").stat()
            stamps.append((suffix, st.st_size, st.st_mtime_ns))
        except OSError:
            stamps.append((suffix, None, None))
    return repr((str(path), stamps))


def _history(db) -> Dict[str, Any]:
    key = _revision(db)
    if key in _CACHE:
        return _CACHE[key]

    with db.connect() as conn:
        rows = pd.read_sql_query(
            """
            SELECT match_id, match_date, home_team_name, away_team_name,
                   home_score, away_score
            FROM matches
            WHERE match_date >= date('now', '-8 years')
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND COALESCE(data_source, '') NOT IN ('simulated', 'upload')
            ORDER BY match_date, match_id
            """, conn,
        )

    elo = defaultdict(lambda: 1500.0)
    games = defaultdict(int)
    snapshots: Dict[tuple, Dict[str, Any]] = {}
    for row in rows.itertuples(index=False):
        home, away = team_core(row.home_team_name), team_core(row.away_team_name)
        if not home or not away or home == away:
            continue
        game_key = (str(row.match_date)[:10], home, away)
        if game_key in snapshots:
            continue
        home_elo, away_elo = elo[home], elo[away]
        snapshots[game_key] = {
            "home_elo": home_elo, "away_elo": away_elo,
            "home_games": games[home], "away_games": games[away],
        }

        hs, aws = int(row.home_score), int(row.away_score)
        actual = 1.0 if hs > aws else 0.5 if hs == aws else 0.0
        expected = 1.0 / (1.0 + 10.0 ** ((away_elo - home_elo) / 400.0))
        margin = max(1, abs(hs - aws))
        multiplier = min(1.5, 1.0 + 0.15 * math.log1p(margin - 1))
        change = 20.0 * multiplier * (actual - expected)
        elo[home] += change
        elo[away] -= change
        games[home] += 1
        games[away] += 1

    result = {"snapshots": snapshots}
    _CACHE.clear()
    _CACHE[key] = result
    return result


def opponent_strength_for_match(db, match_id: int, team_name: str = "") -> Dict[str, Any]:
    """Força do adversário ANTES da partida; sem usar o placar do próprio jogo."""
    with db.connect() as conn:
        target = conn.execute(
            "SELECT match_date, home_team_name, away_team_name FROM matches WHERE match_id=?",
            (int(match_id),),
        ).fetchone()
    if not target:
        return {"elo": None, "jogos_historicos": 0, "nivel": None, "ajuste": 0.0,
                "confianca": "sem dados", "adversario": None}

    match_date, home_name, away_name = target
    home, away = team_core(home_name), team_core(away_name)
    snap = _history(db)["snapshots"].get((str(match_date)[:10], home, away))
    if not snap:
        return {"elo": 1500.0, "jogos_historicos": 0, "nivel": 50.0, "ajuste": 0.0,
                "confianca": "baixa", "adversario": away_name}

    selected = team_core(team_name)
    # A nota é contextualizada pelo adversário de cada equipe, não sempre pelo visitante.
    if selected == away:
        rating, sample, opponent = float(snap["home_elo"]), int(snap["home_games"]), home_name
    else:
        rating, sample, opponent = float(snap["away_elo"]), int(snap["away_games"]), away_name

    # Amostras curtas são encolhidas para a média; a correção máxima é deliberadamente limitada.
    reliability = min(1.0, sample / 8.0)
    effective = 1500.0 + (rating - 1500.0) * reliability
    level = 100.0 / (1.0 + 10.0 ** ((1500.0 - effective) / 400.0))
    adjustment = max(-0.4, min(0.4, (effective - 1500.0) / 400.0 * 0.30)) if sample >= 4 else 0.0
    return {
        "elo": round(effective, 1), "elo_bruto": round(rating, 1),
        "jogos_historicos": sample, "nivel": round(level, 1),
        "ajuste": round(adjustment, 2),
        "confianca": "alta" if sample >= 12 else "média" if sample >= 4 else "baixa",
        "adversario": opponent,
    }
