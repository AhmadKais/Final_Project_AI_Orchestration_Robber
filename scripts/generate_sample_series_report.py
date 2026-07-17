"""Generate a sample full 6-game LEAGUE SERIES report (Appendix F Table 18:
"Games in a series against one opponent" = 6, Fixed) from an ACTUAL played
series -- not fabricated data. Complements generate_sample_reports.py
(which illustrates a single sub-game's four artifacts); this one plays a
real series through the real SeriesRunner (simulation_sdk.py) -- the same
code real league play uses, not a second, parallel implementation of it --
with the real default strategy (MinimaxBrain) on both sides.

Usage:
    uv run python scripts/generate_sample_series_report.py

Writes into docs/sample_reports/series/ (committed, illustrative examples
-- NOT the same as the gitignored logs/ directory, which holds real
per-match runtime artifacts).
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from police_thief.infra.llm.template_provider import TemplateProvider
from police_thief.infra.mcp_client import OpponentClient
from police_thief.infra.mcp_server import MoveMailbox, build_server
from police_thief.shared.config_manager import derive_game_id, load_shared_config
from police_thief.simulation_sdk import SeriesRunner

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "sample_reports" / "series"
CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"


async def play_sample_series() -> tuple[dict, dict]:
    shared_config = load_shared_config(CONFIG_ROOT / "game.json")
    # The book mandates 6 (Appendix F Table 18); the shipped config default
    # is 1 (a single sample match) -- override for this illustration only,
    # never mutating the committed config/game.json itself.
    shared_config = {**shared_config, "network_and_league": {**shared_config["network_and_league"], "num_games": 6}}
    game_id = derive_game_id(shared_config)

    police_mailbox, thief_mailbox = MoveMailbox(), MoveMailbox()
    police_mcp = build_server("police", police_mailbox)
    thief_mcp = build_server("thief", thief_mailbox)

    runner_police = SeriesRunner(
        config_natural_role="police", values=shared_config, mailbox=police_mailbox,
        mcp_client=OpponentClient(thief_mcp, response_timeout_sec=10),
        llm_provider=TemplateProvider(rng=random.Random(10)),
        log_dir=OUT_DIR / "police", game_id=game_id,
        code_version="0.1.0", github_commit="0000000sample",
        group_name="sample-team-police", llm_model="template",
        team_members=["id-1001", "id-1002"], repo_url="https://github.com/example/police-repo",
    )
    runner_thief = SeriesRunner(
        config_natural_role="thief", values=shared_config, mailbox=thief_mailbox,
        mcp_client=OpponentClient(police_mcp, response_timeout_sec=10),
        llm_provider=TemplateProvider(rng=random.Random(20)),
        log_dir=OUT_DIR / "thief", game_id=game_id,
        code_version="0.1.0", github_commit="0000000sample",
        group_name="sample-team-thief", llm_model="template",
        team_members=["id-2001", "id-2002"], repo_url="https://github.com/example/thief-repo",
    )
    result_police, result_thief = await asyncio.gather(runner_police.run(), runner_thief.run())
    return result_police, result_thief


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result_police, result_thief = asyncio.run(play_sample_series())
    print(f"Played a real 6-game series: game_id={result_police['game_id']}")
    for sub_game in result_police["sub_games"]:
        print(
            f"  sub-game {sub_game['sub_game_number']}: police plays {sub_game['my_role']}, "
            f"outcome={sub_game['outcome']}, police {sub_game['my_score']} - "
            f"thief {sub_game['opponent_score']}"
        )
    print(f"Series result: police {result_police['my_total']} - thief {result_police['opponent_total']} "
          f"({result_police['winner']} wins, from police's perspective)")
    print(f"Wrote declaration + {len(result_police['sub_games'])} config/log files + results "
          f"to {OUT_DIR}/police/ and {OUT_DIR}/thief/")


if __name__ == "__main__":
    main()
