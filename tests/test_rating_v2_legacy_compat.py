from src.analytics import rating_v2_legacy as legacy


def test_legacy_rating_scale_remains_reproducible():
    assert legacy.pct_to_score(50) == 5.5
    assert legacy.pct_to_score(90) == 8.5
    assert legacy.pct_to_score(99) == 10.0
    assert legacy.REF_SCORE == 5.5


def test_legacy_role_classifier_and_dimensions_remain_available():
    assert legacy.role_of("Goalkeeper") == "goleiro"
    assert "ofensiva" in legacy.DIMS
    assert len(legacy.PCT_TABLE) >= 9
