from __future__ import annotations

from src.intelligence.fuzzy import mamdani_player_rating, sugeno_pressure


def test_mamdani_returns_explanation_and_not_probability():
    result = mamdani_player_rating(95, 92)
    assert result["model"] == "Mamdani"
    assert result["is_probability"] is False
    assert result["score"] > 80
    assert result["activated_rules"]
    assert any(rule["then"] == "excelente" for rule in result["activated_rules"])


def test_mamdani_low_inputs_are_not_high_contribution():
    low = mamdani_player_rating(5, 10)
    high = mamdani_player_rating(95, 95)
    assert low["score"] < high["score"]
    assert low["is_probability"] is False


def test_sugeno_is_bounded_and_exposes_rule_weights():
    result = sugeno_pressure(70, 65, 50, minute=60)
    assert result["model"] == "Takagi-Sugeno"
    assert 0 <= result["pressure_index"] <= 100
    assert result["rule_weights"]
    assert result["is_probability"] is False
