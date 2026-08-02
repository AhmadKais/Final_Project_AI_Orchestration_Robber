"""End-to-end integration: two Orchestrators (Cop and Robber) play a full
game against each other over the Commit-Reveal protocol, using fastmcp's
in-process transport (no real sockets -- same pattern as
tests/test_mcp_infra.py). This is the proof that every stage's pieces
actually work together, not just in isolation.
"""

import random

from police_thief.domain.rules import GameOutcome
from police_thief.domain.strategy.heuristic_brain import HeuristicBrain
from police_thief.infra.llm.template_provider import TemplateProvider
from police_thief.infra.mcp_client import OpponentClient
from police_thief.infra.mcp_server import MoveMailbox, build_server
from police_thief.interface.replay_viewer import ReplayViewer
from police_thief.peer_runtime.orchestrator import Orchestrator


def make_small_config(max_moves=20):
    return {
        "board_and_agents": {"grid_size": 5, "cop_start": [0, 0], "thief_start": [2, 2]},
        "movement_and_barriers": {"max_barriers": 5, "max_moves": max_moves, "survival_threshold": max_moves},
        "scoring": {
            "capture_cop": 20, "capture_thief": 5,
            "survival_cop": 5, "survival_thief": 10,
            "tie_score": 2, "technical_loss": 0,
        },
        "pheromones": {"pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5},
        "network_and_league": {"response_timeout_sec": 5},
        "world": {"hint_max_words": 15},
    }


def make_matched_pair(tmp_path, max_moves=20):
    """Two Orchestrators wired to each other's in-process FastMCP servers,
    exactly like two real peers -- just without a real socket between them."""
    police_mailbox, thief_mailbox = MoveMailbox(), MoveMailbox()
    police_mcp = build_server("police", police_mailbox)
    thief_mcp = build_server("thief", thief_mailbox)

    config = make_small_config(max_moves)

    police = Orchestrator(
        role="police",
        brain=HeuristicBrain(role="police"),
        mcp_client=OpponentClient(thief_mcp, response_timeout_sec=5),
        mailbox=police_mailbox,
        llm_provider=TemplateProvider(rng=random.Random(1)),
        config=config,
        log_path=tmp_path / "police_match.json",
    )
    thief = Orchestrator(
        role="thief",
        brain=HeuristicBrain(role="thief"),
        mcp_client=OpponentClient(police_mcp, response_timeout_sec=5),
        mailbox=thief_mailbox,
        llm_provider=TemplateProvider(rng=random.Random(2)),
        config=config,
        log_path=tmp_path / "thief_match.json",
    )
    return police, thief


async def test_full_game_terminates_with_a_definite_outcome(tmp_path):
    police, thief = make_matched_pair(tmp_path)

    import asyncio
    police_outcome, thief_outcome = await asyncio.gather(police.run_game(), thief.run_game())

    assert police_outcome in (GameOutcome.CAPTURE, GameOutcome.SURVIVAL)
    assert thief_outcome in (GameOutcome.CAPTURE, GameOutcome.SURVIVAL)
    # Both sides agree on the shape of the outcome (whether or not a
    # capture happened) -- they computed it from the same true, revealed moves.
    assert (police_outcome == GameOutcome.CAPTURE) == (thief_outcome == GameOutcome.CAPTURE)
    assert not police.forgery_detected
    assert not thief.forgery_detected


async def test_full_game_produces_a_cryptographically_verifiable_log(tmp_path):
    police, thief = make_matched_pair(tmp_path)

    import asyncio
    await asyncio.gather(police.run_game(), thief.run_game())

    police_log = ReplayViewer(tmp_path / "police_match.json")
    thief_log = ReplayViewer(tmp_path / "thief_match.json")

    assert police_log.verify_all() is True
    assert thief_log.verify_all() is True
    # Each side's log includes both roles' moves (the full match, not just
    # one side's actions) -- see Orchestrator._write_log.
    roles_seen = {entry["role"] for entry in police_log.load()}
    assert roles_seen == {"police", "thief"}


async def test_close_starting_positions_lead_to_a_quick_capture(tmp_path):
    # Cop and Robber start 4 apart on a barrier-free 5x5 board with no
    # deception (default intent="true") -- HeuristicBrain's Manhattan
    # pursuit should reliably corner the Robber well before max_moves.
    police, thief = make_matched_pair(tmp_path, max_moves=20)

    import asyncio
    police_outcome, _ = await asyncio.gather(police.run_game(), thief.run_game())

    assert police_outcome == GameOutcome.CAPTURE
    assert police.step < 20  # ended before exhausting the step budget


async def test_step0_declarations_are_exchanged_before_the_first_move(tmp_path):
    import asyncio

    police, thief = make_matched_pair(tmp_path)
    await asyncio.gather(police.run_game(), thief.run_game())

    # Each side collected its own declaration and received the other's.
    assert police.own_step0 is not None
    assert thief.own_step0 is not None
    assert police.opponent_step0 is not None
    assert thief.opponent_step0 is not None
    assert police.opponent_step0["group_name"] == thief.own_step0.group_name
    assert thief.opponent_step0["group_name"] == police.own_step0.group_name


async def test_step0_declarations_are_recorded_in_the_log(tmp_path):
    import asyncio
    import json

    police, thief = make_matched_pair(tmp_path)
    await asyncio.gather(police.run_game(), thief.run_game())

    log_data = json.loads((tmp_path / "police_match.json").read_text())
    assert "step0" in log_data
    assert log_data["step0"]["police"] is not None
    assert log_data["step0"]["thief"] is not None


async def test_log_reports_zero_llm_tokens_for_the_zero_token_template_provider(tmp_path):
    police, thief = make_matched_pair(tmp_path)

    import asyncio
    import json

    await asyncio.gather(police.run_game(), thief.run_game())

    log_data = json.loads((tmp_path / "police_match.json").read_text())
    assert log_data["llm_tokens_consumed_this_game"] == 0


async def test_log_reports_this_games_own_token_delta_not_a_running_total(tmp_path):
    # A series shares one LLMProvider instance across every sub-game
    # (SeriesRunner); the per-sub-game log must report just THIS game's
    # tokens, not everything the provider has ever consumed (Rule 54).
    import asyncio

    class StubTokenProvider(TemplateProvider):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        def generate_hint(self, *, prompt, word_limit):
            self.calls += 1
            self._record_tokens(7)
            return super().generate_hint(prompt=prompt, word_limit=word_limit)

    police_mailbox, thief_mailbox = MoveMailbox(), MoveMailbox()
    police_mcp = build_server("police", police_mailbox)
    thief_mcp = build_server("thief", thief_mailbox)
    config = make_small_config(max_moves=20)
    shared_provider = StubTokenProvider(rng=random.Random(1))
    shared_provider._record_tokens(50)  # pretend an earlier sub-game already ran

    police = Orchestrator(
        role="police", brain=HeuristicBrain(role="police"),
        mcp_client=OpponentClient(thief_mcp, response_timeout_sec=5),
        mailbox=police_mailbox, llm_provider=shared_provider, config=config,
        log_path=tmp_path / "police_match.json",
    )
    thief = Orchestrator(
        role="thief", brain=HeuristicBrain(role="thief"),
        mcp_client=OpponentClient(police_mcp, response_timeout_sec=5),
        mailbox=thief_mailbox, llm_provider=TemplateProvider(rng=random.Random(2)),
        config=config, log_path=tmp_path / "thief_match.json",
    )
    await asyncio.gather(police.run_game(), thief.run_game())

    import json
    log_data = json.loads((tmp_path / "police_match.json").read_text())
    # Only tokens recorded AFTER this Orchestrator was constructed count --
    # the pre-existing 50 from the "earlier sub-game" must not leak in.
    assert log_data["llm_tokens_consumed_this_game"] == 7 * shared_provider.calls


async def test_belief_map_converges_toward_the_true_opponent_after_a_turn(tmp_path):
    police, thief = make_matched_pair(tmp_path, max_moves=1)

    import asyncio
    await asyncio.gather(police.run_turn(), thief.run_turn())

    # After one real turn, the Cop's belief should already be concentrated
    # near the Robber's true (revealed) position -- not still uniform.
    assert abs(sum(police.belief.probabilities.values()) - 1.0) < 1e-9
    peak_probability = max(police.belief.probabilities.values())
    uniform_probability = 1.0 / (police.grid_size ** 2)
    assert peak_probability > uniform_probability
