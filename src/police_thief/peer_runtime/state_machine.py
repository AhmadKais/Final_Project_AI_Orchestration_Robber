"""Legal turn-phase state machine (Sec. 8.3, Fig. 11).

WAITING_FOR_OPPONENT -> COMPUTING_MOVE -> COMMITTING -> AWAITING_REVEAL ->
VERIFYING -> (back to WAITING_FOR_OPPONENT), with TECHNICAL_LOSS reachable
from any communication stage. Blocking illegal transitions is the first
line of defense against deadlock (Appendix E rules 4-5).
"""

from __future__ import annotations


class GamePhaseMachine:
    TRANSITIONS = {
        "WAITING_FOR_OPPONENT": {"COMPUTING_MOVE", "TECHNICAL_LOSS"},
        "COMPUTING_MOVE": {"COMMITTING", "TECHNICAL_LOSS"},
        "COMMITTING": {"AWAITING_REVEAL", "TECHNICAL_LOSS"},
        "AWAITING_REVEAL": {"VERIFYING", "TECHNICAL_LOSS"},
        "VERIFYING": {"WAITING_FOR_OPPONENT"},
        "TECHNICAL_LOSS": set(),  # terminal state
    }

    def __init__(self) -> None:
        self.state = "WAITING_FOR_OPPONENT"

    def transition(self, target: str) -> str:
        if target not in self.TRANSITIONS[self.state]:
            raise ValueError(f"Illegal transition: {self.state} -> {target}")
        self.state = target
        return self.state
