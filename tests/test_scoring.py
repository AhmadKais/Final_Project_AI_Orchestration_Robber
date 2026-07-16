"""Scoring table payoffs (Table 2 / Appendix F Table 17 binding defaults)
and series aggregation (Appendix F Table 18: 6 games against one opponent)."""

import pytest

from police_thief.domain.rules import GameOutcome
from police_thief.domain.scoring import (
    aggregate_series,
    effective_role_for_subgame,
    record_sub_game,
    score_outcome,
)

SCORING_CONFIG = {
    "capture_cop": 20,
    "capture_thief": 5,
    "survival_cop": 5,
    "survival_thief": 10,
    "tie_score": 2,
    "technical_loss": 0,
}


def test_capture_scores_favor_cop():
    result = score_outcome(GameOutcome.CAPTURE, SCORING_CONFIG)
    assert result.cop_score == 20
    assert result.thief_score == 5


def test_survival_scores_favor_thief():
    result = score_outcome(GameOutcome.SURVIVAL, SCORING_CONFIG)
    assert result.cop_score == 5
    assert result.thief_score == 10


def test_technical_loss_zeroes_both_sides():
    result = score_outcome(GameOutcome.TECHNICAL_LOSS, SCORING_CONFIG)
    assert result.cop_score == 0
    assert result.thief_score == 0


def test_unknown_outcome_raises():
    with pytest.raises(ValueError):
        score_outcome("not-a-real-outcome", SCORING_CONFIG)


# -- role alternation across a series (Appendix F Table 18) ----------------

def test_odd_subgames_play_the_config_natural_role():
    assert effective_role_for_subgame("police", 1) == "police"
    assert effective_role_for_subgame("police", 3) == "police"
    assert effective_role_for_subgame("thief", 1) == "thief"


def test_even_subgames_play_the_opposite_role():
    assert effective_role_for_subgame("police", 2) == "thief"
    assert effective_role_for_subgame("thief", 2) == "police"


def test_six_game_series_splits_exactly_evenly():
    roles = [effective_role_for_subgame("police", n) for n in range(1, 7)]
    assert roles.count("police") == 3
    assert roles.count("thief") == 3


# -- per-sub-game recording, reoriented into my/opponent units -------------

def test_record_sub_game_as_police_uses_cop_units():
    record = record_sub_game(1, "police", GameOutcome.CAPTURE, SCORING_CONFIG)
    assert record.my_score == 20  # capture_cop
    assert record.opponent_score == 5  # capture_thief


def test_record_sub_game_as_thief_uses_thief_units():
    record = record_sub_game(2, "thief", GameOutcome.CAPTURE, SCORING_CONFIG)
    assert record.my_score == 5  # capture_thief
    assert record.opponent_score == 20  # capture_cop


# -- series aggregation ------------------------------------------------------

def test_aggregate_series_sums_across_subgames():
    records = [
        record_sub_game(1, "police", GameOutcome.CAPTURE, SCORING_CONFIG),  # me 20, opp 5
        record_sub_game(2, "thief", GameOutcome.SURVIVAL, SCORING_CONFIG),  # me 10, opp 5
    ]
    result = aggregate_series(records, tie_score=SCORING_CONFIG["tie_score"])
    assert result.my_total == 30
    assert result.opponent_total == 10
    assert result.winner == "me"


def test_aggregate_series_tie_adds_tie_score_to_both_sides():
    records = [
        record_sub_game(1, "police", GameOutcome.SURVIVAL, SCORING_CONFIG),  # me 5, opp 10
        record_sub_game(2, "thief", GameOutcome.SURVIVAL, SCORING_CONFIG),  # me 10, opp 5
    ]
    result = aggregate_series(records, tie_score=SCORING_CONFIG["tie_score"])
    assert result.my_total == 15 + SCORING_CONFIG["tie_score"]
    assert result.opponent_total == 15 + SCORING_CONFIG["tie_score"]
    assert result.winner == "tie"


def test_aggregate_series_opponent_win():
    records = [record_sub_game(1, "police", GameOutcome.SURVIVAL, SCORING_CONFIG)]  # me 5, opp 10
    result = aggregate_series(records, tie_score=SCORING_CONFIG["tie_score"])
    assert result.winner == "opponent"
