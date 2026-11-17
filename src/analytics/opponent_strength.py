"""Força pré-jogo do adversário por Elo histórico, com deduplicação de partidas por fonte.

O Elo é calculado apenas com placares reais anteriores à partida avaliada. Não usa o resultado
da própria partida para estimar a dificuldade enfrentada pelo atleta.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict

import pandas as pd

from src.data_lake.ids import team_core

_CACHE: Dict[str, Dict[str, Any]] = {}


def _revision(db) -> str:
    path = getattr(db, "db_path", None)
    try:
        stat = path.stat()
        return f"{path}:{stat.st_size}:{stat.st_mtime_ns}"
    except Exception:
        return f"uncacheable:{id(db)}"


def _elo_history(db, target_date: str) -> Dict[str, Any]:
    revision = _revision(db)
    key = f"{revision}:{target_date[:4]}"
    if key in _CACHE:
        return _CACHE[key]

    with db.connect() as conn:
        rows = pd.read_sql_query(
            """
            SELECT match_id, match_date, home_team_name, away_team_name,
                   home_score, away_score, data_source
            FROM matches
            WHERE match_date >= date(?, '-8 years')
              AND match_date <= ?
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND COALESCE(data_source, '') NOT IN ('simulated', 'upload')
            ORDER BY match_date, match_id
            """,
            conn, params=[target_date, target_date],
        )

    elo = defaultdict(lambda: 1500.0)
    games = defaultdict(int)
    seen = set()
    before: Dict[str, Any] = {}
    for row in rows.itertuples(index=False):
        home, away = team_core(row.home_team_name), team_core(row.away_team_name)
        if not home or not away or home == away:
            continue
        date = str(row.match_date or "")[:10]
        game_key = (date, home, away)
        if game_key in seen:
            continue
        seen.add(game_key)
        hs, aws = int(row.home_score), int(row.away_score)
        if hs > aws:
            actual_home = 1.0
        elif hs == aws:
            actual_home = 0.5
        else:
            actual_home = 0.0
        home_elo, away_elo = elo[home], elo[away]
        expected_home = 1.0 / (1.0 + 10.0 ** ((away_elo - home_elo) / 400.0))
        margin = max(1, abs(hs - aws))
        multiplier = min(1.5, 1.0 + 0.15 * math.log1p(margin - 1))
        change = 20.0 * multiplier * (actual_home - expected_home)
        elo[home] += change
        elo[away] -= change
        games[home] += 1
        games[away] += 1

    result = {"elo": dict(elo), "games": dict(games)}
    _CACHE[key] = result
    if len(_CACHE) > 8:
        _CACHE.pop(next(iter(_CACHE)))
    return result


def opponent_strength_for_match(db, match_id: int) -> Dict[str, Any]:
    """Força do adversário antes do jogo; retorna ajuste pequeno e encolhido para amostras curtas."""
    with db.connect() as conn:
        target = conn.execute(
            "SELECT match_date, home_team_name, away_team_name FROM matches WHERE match_id=?",
            (int(match_id),),
        ).fetchone()
    if not target:
        return {"elo": None, "jogos_historicos": 0, "nivel": None, "ajuste": 0.0, "confianca": "sem dados"}
    match_date, home_name, away_name = target
    history = _elo_history(db, str(match_date))
    home, away = team_core(home_name), team_core(away_name)
    elo, games = history["elo"], history["games"]
    # A partida-alvo já pode estar incluída no histórico. Reconstituir o pré-jogo exige
    # excluir o seu resultado; por isso, a função abaixo usa o último snapshot anterior.
    # A versão histórica por data é reconstruída abaixo apenas até o dia anterior para evitar leakage.
    with db.connect() as conn:
        rows = pd.read_sql_query(
            """
            SELECT match_date, home_team_name, away_team_name, home_score, away_score
            FROM matches
            WHERE match_date >= date(?, '-8 years') AND match_date < ?
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND COALESCE(data_source, '') NOT IN ('simulated', 'upload')
            ORDER BY match_date, match_id
            """,
            conn, params=[str(match_date), str(match_date)],
        )
    pre_elo = defaultdict(lambda: 1500.0)
    pre_games = defaultdict(int)
    seen = set()
    for row in rows.itertuples(index=False):
        h, a = team_core(row.home_team_name), team_core(row.away_team_name)
        if not h or not a or h == a:
            continue
        k = (str(row.match_date)[:10], h, a)
        if k in seen:
            continue
        seen.add(k)
        hs, aws = int(row.home_score), int(row.away_score)
        actual = 1.0 if hs > aws else 0.5 if hs == aws else 0.0
        expected = 1.0 / (1.0 + 10.0 ** ((pre_elo[a] - pre_elo[h]) / 400.0))
        margin = max(1, abs(hs - aws))
        factor = min(1.5, 1.0 + 0.15 * math.log1p(margin - 1))
        delta = 20.0 * factor * (actual - expected)
        pre_elo[h] += delta
        pre_elo[a] -= delta
        pre_games[h] += 1
        pre_games[a] += 1

    opponent = away if home else home
    rating = float(pre_elo[opponent])
    sample = int(pre_games[opponent])
    # Shrink ratings de seleções/clubes com poucos jogos para a média global.
    reliability = min(1.0, sample / 8.0)
    effective = 1500.0 + (rating - 1500.0) * reliability
    level = 100.0 / (1.0 + 10.0 ** ((1500.0 - effective) / 400.0))
    adjustment = max(-0.4, min(0.4, (effective - 1500.0) / 400.0 * 0.30)) if sample >= 4 else 0.0
    return {
        "elo": round(effective, 1),
        "elo_bruto": round(rating, 1),
        "jogos_historicos": sample,
        "nivel": round(level, 1),
        "ajuste": round(adjustment, 2),
        "confianca": "alta" if sample >= 12 else "média" if sample >= 4 else "baixa",
        "adversario": away_name if home else home_name,
    }
