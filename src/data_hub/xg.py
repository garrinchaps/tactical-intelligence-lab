"""
xG estimado do laboratório (para fontes sem xG, como o Wyscout aberto).

Regressão logística com distância ao centro do gol, ângulo de visão do gol e
cabeceio, ajustada em finalizações do StatsBomb Open Data (coordenadas 120 x 80).
AUC ≈ 0,79 na amostra de ajuste (xG oficial do StatsBomb: ≈ 0,83). Pênaltis = 0,76.
Sempre rotular como "xG estimado (modelo do laboratório)".
"""

from __future__ import annotations

import math

COEF_DISTANCE = -0.1530
COEF_ANGLE = 0.8277
COEF_HEADER = -1.4277
INTERCEPT = 0.2572
PENALTY_XG = 0.76


def estimate_xg(x: float, y: float, is_header: bool = False, is_penalty: bool = False) -> float:
    if is_penalty:
        return PENALTY_XG
    if x is None or y is None or (isinstance(x, float) and math.isnan(x)):
        return 0.0
    dx = max(120.0 - float(x), 0.1)
    dist = math.hypot(dx, 40.0 - float(y))
    angle = abs(math.atan2(44.0 - float(y), dx) - math.atan2(36.0 - float(y), dx))
    z = INTERCEPT + COEF_DISTANCE * dist + COEF_ANGLE * angle + COEF_HEADER * (1 if is_header else 0)
    return round(1.0 / (1.0 + math.exp(-z)), 4)
