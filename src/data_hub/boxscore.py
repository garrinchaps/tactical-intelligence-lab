"""
Padronização de estatísticas de boxscore entre fontes (API-Football, ESPN...).

Cada fonte usa nomes próprios ("Ball Possession", "possessionPct"...). Aqui tudo vira
uma chave única (`possession_pct`, `shots_total`...) com rótulo em português.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

# chave padrão -> (rótulo pt-BR, maior é melhor?)
STAT_LABELS: Dict[str, Tuple[str, bool]] = {
    "possession_pct": ("Posse de bola (%)", True),
    "xg": ("xG (fonte)", True),
    "shots_total": ("Finalizações", True),
    "shots_on_target": ("Finalizações no gol", True),
    "shots_off_target": ("Finalizações para fora", True),
    "shots_blocked": ("Finalizações bloqueadas", True),
    "shots_inside_box": ("Finalizações dentro da área", True),
    "shots_outside_box": ("Finalizações de fora da área", True),
    "passes_total": ("Passes", True),
    "passes_accurate": ("Passes certos", True),
    "pass_accuracy_pct": ("Precisão de passe (%)", True),
    "crosses_total": ("Cruzamentos", True),
    "crosses_accurate": ("Cruzamentos certos", True),
    "long_balls_total": ("Bolas longas", True),
    "long_balls_accurate": ("Bolas longas certas", True),
    "corners": ("Escanteios", True),
    "offsides": ("Impedimentos", False),
    "fouls": ("Faltas cometidas", False),
    "yellow_cards": ("Cartões amarelos", False),
    "red_cards": ("Cartões vermelhos", False),
    "saves": ("Defesas do goleiro", True),
    "tackles_total": ("Desarmes tentados", True),
    "tackles_won": ("Desarmes certos", True),
    "interceptions": ("Interceptações", True),
    "clearances": ("Cortes", True),
    "goals_prevented": ("Gols evitados (goleiro)", True),
}

API_FOOTBALL_MAP = {
    "Ball Possession": "possession_pct", "Total Shots": "shots_total", "Shots on Goal": "shots_on_target",
    "Shots off Goal": "shots_off_target", "Blocked Shots": "shots_blocked", "Shots insidebox": "shots_inside_box",
    "Shots outsidebox": "shots_outside_box", "Fouls": "fouls", "Corner Kicks": "corners", "Offsides": "offsides",
    "Yellow Cards": "yellow_cards", "Red Cards": "red_cards", "Goalkeeper Saves": "saves",
    "Total passes": "passes_total", "Passes accurate": "passes_accurate", "Passes %": "pass_accuracy_pct",
    "expected_goals": "xg", "goals_prevented": "goals_prevented",
}

ESPN_MAP = {
    "possessionPct": "possession_pct", "totalShots": "shots_total", "shotsOnTarget": "shots_on_target",
    "blockedShots": "shots_blocked", "wonCorners": "corners", "foulsCommitted": "fouls", "offsides": "offsides",
    "yellowCards": "yellow_cards", "redCards": "red_cards", "saves": "saves", "totalPasses": "passes_total",
    "accuratePasses": "passes_accurate", "passPct": "pass_accuracy_pct", "totalCrosses": "crosses_total",
    "accurateCrosses": "crosses_accurate", "totalLongBalls": "long_balls_total",
    "accurateLongBalls": "long_balls_accurate", "totalTackles": "tackles_total", "effectiveTackles": "tackles_won",
    "interceptions": "interceptions", "totalClearance": "clearances",
}


def parse_number(value: Any) -> Optional[float]:
    """'55%' -> 55.0 ; '0.83' -> 0.83 ; None -> None ; 12 -> 12.0"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not m:
        return None
    num = float(m.group(0).replace(",", "."))
    return num


def stat_row(team: str, key: str, raw_value: Any) -> Optional[Dict[str, Any]]:
    val = parse_number(raw_value)
    if val is None:
        return None
    if key == "pass_accuracy_pct" and val <= 1.0:
        val = round(val * 100.0, 1)  # ESPN às vezes manda 0.85
    label = STAT_LABELS.get(key, (key, True))[0]
    return {"team_name": team, "stat_key": key, "stat_label": label, "value": val,
            "display_value": str(raw_value)}
