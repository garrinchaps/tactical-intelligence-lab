import math

import pandas as pd

from src.scout.engine import apply_votes, normalize_vote_counts


def test_normalize_vote_counts_accepts_pairs_and_rejects_scalar_values():
    assert normalize_vote_counts((3, 2)) == (3, 2)
    assert normalize_vote_counts(["4", "1"]) == (4, 1)
    assert normalize_vote_counts((None, 2)) == (0, 2)
    assert normalize_vote_counts(2.5) == (0, 0)
    assert normalize_vote_counts(float("nan")) == (0, 0)
    assert normalize_vote_counts(math.inf) == (0, 0)


def test_apply_votes_replaces_legacy_scalar_column_with_pairs():
    ranked = pd.DataFrame({
        "nome": ["Jogador A", "Jogador B"],
        "_core": ["jogador a", "jogador b"],
        "score_scout": [10.0, 8.0],
        "votos_scout": [2.5, float("nan")],
    })

    result = apply_votes(ranked, {})

    assert result["votos_scout"].tolist() == [(0, 0), (0, 0)]
    assert result["score_scout"].tolist() == [10.0, 8.0]


def test_apply_votes_keeps_valid_pairs_and_ignores_malformed_feedback():
    ranked = pd.DataFrame({
        "nome": ["Jogador A", "Jogador B"],
        "_core": ["jogador a", "jogador b"],
        "score_scout": [10.0, 8.0],
        "votos_scout": [0.0, 0.0],
    })

    result = apply_votes(ranked, {"jogador a": (2, 1), "jogador b": 7.0})
    by_name = result.set_index("nome")

    assert by_name.loc["Jogador A", "votos_scout"] == (2, 1)
    assert by_name.loc["Jogador B", "votos_scout"] == (0, 0)
    assert by_name.loc["Jogador A", "score_scout"] == 13.0
    assert by_name.loc["Jogador B", "score_scout"] == 8.0
