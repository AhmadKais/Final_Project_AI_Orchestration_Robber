"""End-to-end: two SeriesRunners play a full multi-sub-game series against
each other (Appendix F Table 18: "Games in a series against one opponent"
= 6, Fixed), using the same in-process FastMCP transport pattern as
tests/test_orchestrator_integration.py. Proves role alternation, mutual
score consistency, and all four Sec. 9.3 per-series JSON artifacts -- not
just that each sub-game in isolation still works (that's already covered).
"""

import asyncio
import json
import random

import pytest

from police_thief.domain.strategy.heuristic_brain import HeuristicBrain
from police_thief.infra.llm.template_provider import TemplateProvider
from police_thief.infra.mcp_client import OpponentClient
from police_thief.infra.mcp_server import MoveMailbox, build_server
from police_thief.simulation_sdk import SeriesRunner


def make_small_config(num_games: int):
    return {
        "board_and_agents": {"grid_size": 5, "cop_start": [0, 0], "thief_start": [2, 2]},
        "movement_and_barriers": {"max_barriers": 5, "max_moves": 20, "survival_threshold": 20},
        "scoring": {
            "capture_cop": 20, "capture_thief": 5,
            "survival_cop": 5, "survival_thief": 10,
            "tie_score": 2, "technical_loss": 0,
        },
        "pheromones": {"pheromone_center_intensity": 0.9, "pheromone_decay": 0.10, "pheromone_grid_size": 5},
        "network_and_league": {"response_timeout_sec": 5, "num_games": num_games},
        "world": {"hint_max_words": 15},
        "strategy": {},  # empty -- SeriesRunner's _build_brain falls back to the shipped default
    }


def make_matched_series(tmp_path, num_games: int, config_natural_roles=("police", "thief")):
    """Two SeriesRunners wired to each other's in-process FastMCP servers,
    same in-process pattern as test_orchestrator_integration.make_matched_pair,
    just wrapping a whole series instead of one Orchestrator."""
    mailbox_a, mailbox_b = MoveMailbox(), MoveMailbox()
    mcp_a = build_server("peer-a", mailbox_a)
    mcp_b = build_server("peer-b", mailbox_b)

    config = make_small_config(num_games)
    role_a, role_b = config_natural_roles

    runner_a = SeriesRunner(
        config_natural_role=role_a, values=config, mailbox=mailbox_a,
        mcp_client=OpponentClient(mcp_b, response_timeout_sec=5),
        llm_provider=TemplateProvider(rng=random.Random(1)),
        log_dir=tmp_path / "a", game_id="test-game",
        code_version="0.0.0-test", github_commit="testcommit",
        group_name="group-a", llm_model="none",
    )
    runner_b = SeriesRunner(
        config_natural_role=role_b, values=config, mailbox=mailbox_b,
        mcp_client=OpponentClient(mcp_a, response_timeout_sec=5),
        llm_provider=TemplateProvider(rng=random.Random(2)),
        log_dir=tmp_path / "b", game_id="test-game",
        code_version="0.0.0-test", github_commit="testcommit",
        group_name="group-b", llm_model="none",
    )
    return runner_a, runner_b


async def test_series_plays_every_subgame_and_writes_results(tmp_path):
    runner_a, runner_b = make_matched_series(tmp_path, num_games=4)

    result_a, result_b = await asyncio.gather(runner_a.run(), runner_b.run())

    assert len(result_a["sub_games"]) == 4
    assert len(result_b["sub_games"]) == 4
    assert (tmp_path / "a" / "result_test-game.json").exists()
    assert (tmp_path / "b" / "result_test-game.json").exists()
    # Every sub-game produced its own named log (Sec. 9.3 file-naming).
    for n in range(1, 5):
        assert (tmp_path / "a" / f"log_test-game_g{n:02d}.json").exists()


async def test_series_alternates_roles_evenly(tmp_path):
    runner_a, runner_b = make_matched_series(tmp_path, num_games=4)

    result_a, result_b = await asyncio.gather(runner_a.run(), runner_b.run())

    roles_a = [g["my_role"] for g in result_a["sub_games"]]
    assert roles_a == ["police", "thief", "police", "thief"]  # A's config-natural role is police
    roles_b = [g["my_role"] for g in result_b["sub_games"]]
    assert roles_b == ["thief", "police", "thief", "police"]  # B's config-natural role is thief
    # The two sides are never on the same role in the same sub-game.
    for role_a, role_b in zip(roles_a, roles_b):
        assert role_a != role_b


async def test_series_scores_are_mutually_consistent(tmp_path):
    """What A calls "my_score" in sub-game N must equal what B calls
    "opponent_score" in that same sub-game -- both sides independently
    computed the same real outcome from the same real revealed moves."""
    runner_a, runner_b = make_matched_series(tmp_path, num_games=4)

    result_a, result_b = await asyncio.gather(runner_a.run(), runner_b.run())

    for sub_a, sub_b in zip(result_a["sub_games"], result_b["sub_games"]):
        assert sub_a["sub_game_number"] == sub_b["sub_game_number"]
        assert sub_a["my_score"] == sub_b["opponent_score"]
        assert sub_b["my_score"] == sub_a["opponent_score"]

    # Series totals follow from the same invariant, before any tie bonus.
    tie_score = 2
    raw_a = result_a["my_total"] - (tie_score if result_a["winner"] == "tie" else 0)
    raw_b_opp = result_b["opponent_total"] - (tie_score if result_b["winner"] == "tie" else 0)
    assert raw_a == raw_b_opp


async def test_series_of_one_game_behaves_like_a_single_game(tmp_path):
    """num_games=1 (the shipped config default) degrades to exactly one
    sub-game -- the series machinery doesn't change single-game behavior."""
    runner_a, runner_b = make_matched_series(tmp_path, num_games=1)

    result_a, result_b = await asyncio.gather(runner_a.run(), runner_b.run())

    assert len(result_a["sub_games"]) == 1
    assert result_a["sub_games"][0]["my_role"] == "police"
    assert result_a["winner"] in ("me", "opponent", "tie")


# -- the other three Sec. 9.3 artifacts: declaration + per-subgame config --

async def test_series_writes_declaration_with_real_hardware(tmp_path):
    runner_a, runner_b = make_matched_series(tmp_path, num_games=2)

    await asyncio.gather(runner_a.run(), runner_b.run())

    declaration = json.loads((tmp_path / "a" / "declaration_test-game.json").read_text())
    assert declaration["game_id"] == "test-game"
    assert declaration["num_games"] == 2
    assert declaration["teams"]["police"]["group_name"] == "group-a"
    # Real Step-0 hardware from sub-game 1's actual exchange, not a placeholder.
    assert declaration["hardware"]["police"]["cpu_cores"] > 0
    assert declaration["hardware"]["thief"] is not None


async def test_series_writes_one_named_config_snapshot_per_subgame(tmp_path):
    runner_a, runner_b = make_matched_series(tmp_path, num_games=3)

    await asyncio.gather(runner_a.run(), runner_b.run())

    for n in range(1, 4):
        config_path = tmp_path / "a" / f"config_test-game_g{n:02d}.json"
        assert config_path.exists()
        assert json.loads(config_path.read_text())["board_and_agents"]["grid_size"] == 5


async def test_series_declaration_includes_supplied_team_identity(tmp_path):
    mailbox_a, mailbox_b = MoveMailbox(), MoveMailbox()
    mcp_a = build_server("peer-a", mailbox_a)
    mcp_b = build_server("peer-b", mailbox_b)
    config = make_small_config(num_games=1)

    runner_a = SeriesRunner(
        config_natural_role="police", values=config, mailbox=mailbox_a,
        mcp_client=OpponentClient(mcp_b, response_timeout_sec=5),
        llm_provider=TemplateProvider(rng=random.Random(1)),
        log_dir=tmp_path / "a", game_id="test-game",
        code_version="0.0.0-test", github_commit="testcommit",
        group_name="group-a", llm_model="none",
        team_members=["id-1001", "id-1002"], repo_url="https://github.com/example/police-repo",
    )
    runner_b = SeriesRunner(
        config_natural_role="thief", values=config, mailbox=mailbox_b,
        mcp_client=OpponentClient(mcp_a, response_timeout_sec=5),
        llm_provider=TemplateProvider(rng=random.Random(2)),
        log_dir=tmp_path / "b", game_id="test-game",
        code_version="0.0.0-test", github_commit="testcommit",
        group_name="group-b", llm_model="none",
    )
    await asyncio.gather(runner_a.run(), runner_b.run())

    declaration = json.loads((tmp_path / "a" / "declaration_test-game.json").read_text())
    assert declaration["teams"]["police"]["members"] == ["id-1001", "id-1002"]
    assert declaration["teams"]["police"]["repo"] == "https://github.com/example/police-repo"
