"""--min-score must reach the acceptance check.

The flag was parsed and dropped, so the threshold stayed hard-coded. It also
must not be confused with _PRIMARY_ONLY_SCORE, which is a constant of the
scoring scheme rather than a threshold.
"""

import inspect

import enrich_greek_from_oca as eg


def test_enrich_accepts_a_min_score():
    assert "min_score" in inspect.signature(eg.enrich).parameters


def test_default_min_score_preserves_previous_behaviour():
    assert eg.enrich.__defaults__ is not None
    assert inspect.signature(eg.enrich).parameters["min_score"].default == 0.5


def test_primary_only_score_is_a_separate_constant():
    # Both happen to be 0.5 today; they must stay independently addressable so
    # raising the threshold does not disable the ambiguity guard.
    assert eg._PRIMARY_ONLY_SCORE == 0.5
    assert eg.DEFAULT_MIN_SCORE == 0.5


def test_acceptance_check_uses_the_parameter_not_a_literal():
    source = inspect.getsource(eg.enrich)
    assert "best_score >= min_score" in source
    assert "best_score >= 0.5" not in source


def test_ambiguity_guard_still_keys_off_the_structural_score():
    source = inspect.getsource(eg.enrich)
    assert "best_score == _PRIMARY_ONLY_SCORE" in source


def test_a_primary_only_match_scores_exactly_the_structural_value():
    # Same primary stem, secondary tokens that share nothing: the case the
    # ambiguity guard exists to catch.
    assert eg._match_score("Gregory of Nyssa", "Gregory of Sinai") == eg._PRIMARY_ONLY_SCORE


def test_an_exact_match_scores_above_the_structural_value():
    assert eg._match_score("Gregory of Nyssa", "Gregory of Nyssa") > eg._PRIMARY_ONLY_SCORE


def test_a_differing_primary_scores_zero():
    assert eg._match_score("Gregory of Nyssa", "Basil of Caesarea") == 0.0


def test_raising_the_threshold_would_reject_a_primary_only_match():
    # What --min-score is for: 0.5 accepts a primary-only match, 0.7 does not.
    score = eg._match_score("Gregory of Nyssa", "Gregory of Sinai")
    assert score >= eg.DEFAULT_MIN_SCORE
    assert not score >= 0.7
