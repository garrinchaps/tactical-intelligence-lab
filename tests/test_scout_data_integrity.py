import pandas as pd

from src.scout.engine import _boolean_mask


def test_boolean_mask_handles_sqlite_integer_flags():
    values = pd.Series([0, 1, None, 0, 1], dtype="Int64")
    assert _boolean_mask(values).tolist() == [False, True, False, False, True]


def test_boolean_mask_handles_text_flags_without_truthy_false_strings():
    values = pd.Series(["false", "TRUE", "0", "sim", None, "não"], dtype="string")
    assert _boolean_mask(values).tolist() == [False, True, False, True, False, False]


def test_boolean_mask_preserves_boolean_flags():
    values = pd.Series([False, True, None], dtype="boolean")
    assert _boolean_mask(values).tolist() == [False, True, False]


def test_team_match_filter_exposes_all_data_depths():
    from src.ui.pages.clubs import filter_team_matches

    matches = pd.DataFrame({
        "match_id": [1, 2, 3, 4],
        "data_level": ["EVENTS", "BOXSCORE", "RESULT", "EVENTS"],
    })

    assert filter_team_matches(matches)["match_id"].tolist() == [1, 2, 3, 4]
    assert filter_team_matches(matches, "Somente com lances")["match_id"].tolist() == [1, 4]
    assert filter_team_matches(matches, "Somente com estatísticas")["match_id"].tolist() == [2]
    assert filter_team_matches(matches, "Somente placares")["match_id"].tolist() == [3]
