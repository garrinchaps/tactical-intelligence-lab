"""
Formações e encaixe de posições.

Coordenadas no campo 120×80 (StatsBomb): o time ataca para a DIREITA; y pequeno = lado ESQUERDO do time.
Cada vaga tem um papel (GK, CB, LB...) e o encaixe de cada posição do Transfermarkt nesse papel vai de 0 a 1.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

Slot = Tuple[str, float, float]          # (papel, x, y)

FORMATIONS: Dict[str, List[Slot]] = {
    "4-3-3": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70),
              ("CM", 52, 24), ("DM", 44, 40), ("CM", 52, 56), ("LW", 86, 12), ("ST", 96, 40), ("RW", 86, 68)],
    "4-4-2": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70),
              ("LM", 60, 12), ("CM", 52, 32), ("CM", 52, 48), ("RM", 60, 68), ("ST", 92, 32), ("ST", 92, 48)],
    "4-2-3-1": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70),
                ("DM", 44, 32), ("DM", 44, 48), ("LW", 76, 12), ("AM", 74, 40), ("RW", 76, 68), ("ST", 98, 40)],
    "4-1-4-1": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70), ("DM", 42, 40),
                ("LM", 66, 12), ("CM", 60, 30), ("CM", 60, 50), ("RM", 66, 68), ("ST", 96, 40)],
    "4-3-1-2": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70),
                ("CM", 50, 24), ("DM", 44, 40), ("CM", 50, 56), ("AM", 72, 40), ("ST", 94, 32), ("ST", 94, 48)],
    "3-5-2": [("GK", 6, 40), ("CB", 24, 22), ("CB", 22, 40), ("CB", 24, 58), ("LWB", 52, 8), ("CM", 54, 28),
              ("DM", 46, 40), ("CM", 54, 52), ("RWB", 52, 72), ("ST", 92, 32), ("ST", 92, 48)],
    "3-4-3": [("GK", 6, 40), ("CB", 24, 22), ("CB", 22, 40), ("CB", 24, 58), ("LWB", 52, 8), ("CM", 50, 32),
              ("CM", 50, 48), ("RWB", 52, 72), ("LW", 86, 14), ("ST", 96, 40), ("RW", 86, 66)],
    "5-3-2": [("GK", 6, 40), ("LWB", 34, 8), ("CB", 24, 24), ("CB", 22, 40), ("CB", 24, 56), ("RWB", 34, 72),
              ("CM", 54, 26), ("DM", 46, 40), ("CM", 54, 54), ("ST", 90, 32), ("ST", 90, 48)],
    # v36: mais desenhos
    "4-4-1-1": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70),
                ("LM", 58, 12), ("CM", 50, 32), ("CM", 50, 48), ("RM", 58, 68), ("AM", 78, 40), ("ST", 96, 40)],
    "4-3-2-1": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70),
                ("CM", 50, 24), ("DM", 44, 40), ("CM", 50, 56), ("AM", 76, 28), ("AM", 76, 52), ("ST", 96, 40)],
    "4-1-2-1-2": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70), ("DM", 42, 40),
                  ("CM", 56, 26), ("CM", 56, 54), ("AM", 72, 40), ("ST", 94, 32), ("ST", 94, 48)],
    "4-2-2-2": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70),
                ("DM", 44, 32), ("DM", 44, 48), ("AM", 72, 20), ("AM", 72, 60), ("ST", 94, 32), ("ST", 94, 48)],
    "3-4-2-1": [("GK", 6, 40), ("CB", 24, 22), ("CB", 22, 40), ("CB", 24, 58), ("LWB", 52, 8), ("CM", 48, 32),
                ("CM", 48, 48), ("RWB", 52, 72), ("AM", 76, 28), ("AM", 76, 52), ("ST", 96, 40)],
    "3-1-4-2": [("GK", 6, 40), ("CB", 24, 22), ("CB", 22, 40), ("CB", 24, 58), ("DM", 40, 40), ("LWB", 56, 8),
                ("CM", 56, 30), ("CM", 56, 50), ("RWB", 56, 72), ("ST", 92, 32), ("ST", 92, 48)],
    "5-4-1": [("GK", 6, 40), ("LWB", 32, 8), ("CB", 24, 24), ("CB", 22, 40), ("CB", 24, 56), ("RWB", 32, 72),
              ("LM", 56, 14), ("CM", 50, 32), ("CM", 50, 48), ("RM", 56, 66), ("ST", 92, 40)],
    "4-5-1": [("GK", 6, 40), ("LB", 30, 10), ("CB", 24, 30), ("CB", 24, 50), ("RB", 30, 70), ("LM", 60, 12),
              ("CM", 54, 28), ("DM", 46, 40), ("CM", 54, 52), ("RM", 60, 68), ("ST", 94, 40)],
}

ROLE_PT = {"GK": "Goleiro", "CB": "Zagueiro", "LB": "Lateral esq.", "RB": "Lateral dir.", "LWB": "Ala esq.",
           "RWB": "Ala dir.", "DM": "Volante", "CM": "Meio-campo", "AM": "Meia", "LM": "Meia esq.", "RM": "Meia dir.",
           "LW": "Ponta esq.", "RW": "Ponta dir.", "ST": "Centroavante"}

# posição detalhada do Transfermarkt (sub_position) e de outras fontes → papel principal
SUBPOS_ROLE = {
    "goalkeeper": "GK", "centre-back": "CB", "left-back": "LB", "right-back": "RB", "defensive midfield": "DM",
    "central midfield": "CM", "attacking midfield": "AM", "left midfield": "LM", "right midfield": "RM",
    "left winger": "LW", "right winger": "RW", "second striker": "ST", "centre-forward": "ST",
    # rótulos de escalação (ESPN, API-Football, StatsBomb) e em português
    "g": "GK", "gk": "GK", "goleiro": "GK", "d": "CB", "cb": "CB", "zagueiro": "CB", "lb": "LB", "rb": "RB",
    "lateral esquerdo": "LB", "lateral direito": "RB", "m": "CM", "cm": "CM", "dm": "DM", "cdm": "DM", "volante": "DM",
    "am": "AM", "cam": "AM", "meia": "AM", "lm": "LM", "rm": "RM", "lw": "LW", "rw": "RW", "f": "ST", "fw": "ST",
    "st": "ST", "cf": "ST", "atacante": "ST", "centroavante": "ST", "ponta esquerda": "LW", "ponta direita": "RW",
    "defender": "CB", "midfield": "CM", "attack": "ST", "lwb": "LWB", "rwb": "RWB",
}
GROUP_ROLE = {"goalkeeper": "GK", "defender": "CB", "midfield": "CM", "attack": "ST"}

# encaixe papel-da-vaga × papel-natural (1 = posição de origem; o resto é adaptação)
_FIT = {
    "GK": {"GK": 1.0},
    "CB": {"CB": 1.0, "DM": 0.7, "LB": 0.55, "RB": 0.55, "LWB": 0.45, "RWB": 0.45},
    "LB": {"LB": 1.0, "LWB": 0.9, "LM": 0.65, "CB": 0.6, "RB": 0.55, "LW": 0.45},
    "RB": {"RB": 1.0, "RWB": 0.9, "RM": 0.65, "CB": 0.6, "LB": 0.55, "RW": 0.45},
    "LWB": {"LWB": 1.0, "LB": 0.9, "LM": 0.85, "LW": 0.7, "RWB": 0.55},
    "RWB": {"RWB": 1.0, "RB": 0.9, "RM": 0.85, "RW": 0.7, "LWB": 0.55},
    "DM": {"DM": 1.0, "CM": 0.85, "CB": 0.65, "AM": 0.5},
    "CM": {"CM": 1.0, "DM": 0.85, "AM": 0.85, "LM": 0.65, "RM": 0.65},
    "AM": {"AM": 1.0, "CM": 0.8, "ST": 0.7, "LW": 0.7, "RW": 0.7, "LM": 0.6, "RM": 0.6},
    "LM": {"LM": 1.0, "LW": 0.9, "LWB": 0.75, "CM": 0.65, "AM": 0.6, "RM": 0.6, "LB": 0.55},
    "RM": {"RM": 1.0, "RW": 0.9, "RWB": 0.75, "CM": 0.65, "AM": 0.6, "LM": 0.6, "RB": 0.55},
    "LW": {"LW": 1.0, "LM": 0.9, "RW": 0.75, "AM": 0.7, "ST": 0.65},
    "RW": {"RW": 1.0, "RM": 0.9, "LW": 0.75, "AM": 0.7, "ST": 0.65},
    "ST": {"ST": 1.0, "AM": 0.65, "LW": 0.6, "RW": 0.6},
}


def natural_role(sub_position: object = "", position: object = "") -> str:
    for v in (sub_position, position):
        k = str(v or "").strip().lower()
        if k in SUBPOS_ROLE:
            return SUBPOS_ROLE[k]
        if k in GROUP_ROLE:
            return GROUP_ROLE[k]
    return ""


def fit(slot_role: str, player_role: str) -> float:
    if not player_role:
        return 0.35                                   # posição desconhecida: possível, mas último recurso
    return _FIT.get(slot_role, {}).get(player_role, 0.15 if "GK" not in (slot_role, player_role) else 0.0)
