"""Translate a GameOutcome into the asymmetric point award (Table 2 / Appendix F Table 17),
and aggregate a whole series' worth of sub-games into one result (Appendix F
Table 18: "Games in a series against one opponent" = 6, Fixed).

Defaults (all "Fixed" in Appendix F): capture_cop=20, capture_thief=5,
survival_cop=5, survival_thief=10, tie_score=2, technical_loss=0.
"""

from __future__ import annotations

from dataclasses import dataclass

from police_thief.domain.rules import GameOutcome

_OPPOSITE_ROLE = {"police": "thief", "thief": "police"}


@dataclass(frozen=True)
class ScoreResult:
    cop_score: int
    thief_score: int


def score_outcome(outcome: GameOutcome, scoring_config: dict) -> ScoreResult:
    """Look up the asymmetric payoff for `outcome` in `scoring_config`
    (the "scoring" section of config/game.json: capture_cop, capture_thief,
    survival_cop, survival_thief, technical_loss)."""
    if outcome == GameOutcome.CAPTURE:
        return ScoreResult(
            cop_score=scoring_config["capture_cop"],
            thief_score=scoring_config["capture_thief"],
        )
    if outcome == GameOutcome.SURVIVAL:
        return ScoreResult(
            cop_score=scoring_config["survival_cop"],
            thief_score=scoring_config["survival_thief"],
        )
    if outcome == GameOutcome.TECHNICAL_LOSS:
        loss = scoring_config["technical_loss"]
        return ScoreResult(cop_score=loss, thief_score=loss)
    raise ValueError(f"Unknown outcome: {outcome!r}")


def effective_role_for_subgame(config_natural_role: str, sub_game_number: int) -> str:
    """This peer's role for sub-game `sub_game_number` (1-indexed) of a
    series. Odd sub-games play the config-natural role; even sub-games
    play the opposite -- an even split of both roles across a full series,
    since Cop and Thief have structurally different objectives and giving
    one team the same role for the whole series would make it an unfair
    comparison. The spec mandates the 6-game series itself (Appendix F
    Table 18) but doesn't spell out an exact alternation rule; this is a
    documented, self-consistent choice, not a literal spec quote."""
    if sub_game_number % 2 == 1:
        return config_natural_role
    return _OPPOSITE_ROLE[config_natural_role]


@dataclass(frozen=True)
class SubGameRecord:
    sub_game_number: int
    my_role: str
    outcome: str
    my_score: int
    opponent_score: int


@dataclass(frozen=True)
class SeriesResult:
    my_total: int
    opponent_total: int
    winner: str  # "me" | "opponent" | "tie"
    sub_games: tuple[SubGameRecord, ...]


def record_sub_game(sub_game_number: int, my_role: str, outcome: GameOutcome, scoring_config: dict) -> SubGameRecord:
    """One sub-game's outcome, reoriented from cop/thief units into this
    peer's own my_score/opponent_score -- what the series aggregate and
    the per-team results report actually need, since `my_role` changes
    across the series."""
    score = score_outcome(outcome, scoring_config)
    my_score, opponent_score = (
        (score.cop_score, score.thief_score) if my_role == "police" else (score.thief_score, score.cop_score)
    )
    return SubGameRecord(
        sub_game_number=sub_game_number, my_role=my_role, outcome=outcome.value,
        my_score=my_score, opponent_score=opponent_score,
    )


def aggregate_series(sub_games: list[SubGameRecord], tie_score: int) -> SeriesResult:
    """Sum a series' sub-game scores into the final result (Sec. 9.3's
    [results file]: "each team's score in each mini-game and the
    cumulative result"). On an aggregate tie, both sides get `tie_score`
    added (Appendix F Table 17 row 5: "Score for each side when the
    cumulative score of all games against an opponent ends in a tie")."""
    my_total = sum(record.my_score for record in sub_games)
    opponent_total = sum(record.opponent_score for record in sub_games)
    if my_total == opponent_total:
        return SeriesResult(
            my_total=my_total + tie_score, opponent_total=opponent_total + tie_score,
            winner="tie", sub_games=tuple(sub_games),
        )
    winner = "me" if my_total > opponent_total else "opponent"
    return SeriesResult(my_total=my_total, opponent_total=opponent_total, winner=winner, sub_games=tuple(sub_games))
