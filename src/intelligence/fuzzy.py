"""Sistemas fuzzy explicáveis para ratings e indicadores de partida.

Os valores retornados são graus/índices fuzzy, nunca probabilidades. As regras
são versionadas no código e a resposta carrega as regras ativadas para permitir
auditoria acadêmica e funcional.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


FUZZY_VERSION = "mamdani-sugeno-v1"


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(np.clip(float(value), low, high))


def triangular(value: float, left: float, peak: float, right: float) -> float:
    x = float(value)
    if x <= left or x >= right:
        return 1.0 if x == peak else 0.0
    if x == peak:
        return 1.0
    return (x - left) / (peak - left) if x < peak else (right - x) / (right - peak)


def player_memberships(value: float) -> dict[str, float]:
    x = _clamp(value)
    return {
        "baixo": round(triangular(x, 0, 0, 50), 6),
        "medio": round(triangular(x, 20, 50, 80), 6),
        "alto": round(triangular(x, 50, 100, 100), 6),
    }


@dataclass(frozen=True)
class FuzzyRule:
    name: str
    intensity: str
    passing: str
    consequent: str


PLAYER_RULES = (
    FuzzyRule("intensidade alta + passe excelente", "alto", "alto", "excelente"),
    FuzzyRule("intensidade alta + passe médio", "alto", "medio", "muito_bom"),
    FuzzyRule("intensidade média + passe alto", "medio", "alto", "muito_bom"),
    FuzzyRule("intensidade média + passe médio", "medio", "medio", "bom"),
    FuzzyRule("intensidade baixa + passe baixo", "baixo", "baixo", "baixo"),
    FuzzyRule("intensidade baixa + passe médio", "baixo", "medio", "regular"),
)


def mamdani_player_rating(defensive_intensity: float, pass_accuracy: float) -> dict[str, Any]:
    """Avalia contribuição tática por inferência Mamdani e centroide."""
    intensity = player_memberships(defensive_intensity)
    passing = player_memberships(pass_accuracy)
    output_centers = {"baixo": 20.0, "regular": 40.0, "bom": 60.0, "muito_bom": 80.0, "excelente": 95.0}
    aggregate = {key: 0.0 for key in output_centers}
    activated: list[dict[str, Any]] = []
    for rule in PLAYER_RULES:
        strength = min(intensity[rule.intensity], passing[rule.passing])
        if strength > 0:
            aggregate[rule.consequent] = max(aggregate[rule.consequent], strength)
            activated.append({"rule": rule.name, "strength": round(strength, 6), "then": rule.consequent})
    denominator = sum(aggregate.values())
    score = sum(output_centers[key] * value for key, value in aggregate.items()) / denominator if denominator else 50.0
    return {
        "model": "Mamdani",
        "version": FUZZY_VERSION,
        "score": round(float(score), 4),
        "is_probability": False,
        "input_memberships": {"defensive_intensity": intensity, "pass_accuracy": passing},
        "output_activation": {key: round(value, 6) for key, value in aggregate.items()},
        "activated_rules": activated,
        "explanation": "Índice fuzzy de contribuição tática; não representa probabilidade.",
    }


def sugeno_pressure(
    possession_pct: float,
    territorial_entries: float,
    shots: float,
    *,
    minute: float = 0.0,
) -> dict[str, Any]:
    """Índice Takagi–Sugeno de pressão, com consequentes lineares."""
    possession = _clamp(possession_pct)
    entries = _clamp(territorial_entries)
    shot_rate = _clamp(shots)
    progress = _clamp(minute, 0, 120) / 120.0
    weights = {
        "dominio territorial": min(possession / 100.0, entries / 100.0),
        "volume de finalizações": min(shot_rate / 100.0, 1.0),
        "pressao equilibrada": max(0.0, 1.0 - abs(possession - entries) / 100.0),
    }
    consequent = {
        "dominio territorial": 0.55 * possession + 0.35 * entries + 10.0 * progress,
        "volume de finalizações": 0.30 * possession + 0.30 * entries + 0.40 * shot_rate,
        "pressao equilibrada": 0.45 * possession + 0.35 * entries + 0.20 * shot_rate,
    }
    total = sum(weights.values())
    score = sum(weights[name] * consequent[name] for name in weights) / total if total else 0.0
    return {
        "model": "Takagi-Sugeno",
        "version": FUZZY_VERSION,
        "pressure_index": round(float(_clamp(score)), 4),
        "is_probability": False,
        "rule_weights": {name: round(value, 6) for name, value in weights.items()},
        "consequents": {name: round(value, 4) for name, value in consequent.items()},
        "explanation": "Índice contínuo de pressão territorial; não representa probabilidade de gol.",
    }
