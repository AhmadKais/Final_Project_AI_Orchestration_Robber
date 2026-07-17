"""CLI entry point (Appendix D Sec. 3):

    uv run python -m police_thief peer --role police                # one game
    uv run python -m police_thief peer --role thief --series         # the real league format --
                                                                       # Appendix F Table 18's mandatory
                                                                       # 6-game series, role alternating
    uv run python -m police_thief replay --log logs/police_match.json
    uv run python -m police_thief report --role police               # email/draft the mandatory
                                                                       # Sec. 9.3 report artifacts
"""

from __future__ import annotations

import argparse
from pathlib import Path

from police_thief.simulation_sdk import run_peer, run_peer_series, run_replay, run_report


def main() -> None:
    parser = argparse.ArgumentParser(prog="police_thief")
    sub = parser.add_subparsers(dest="command", required=True)

    peer_cmd = sub.add_parser("peer", help="Run one peer (police or thief).")
    peer_cmd.add_argument("--role", choices=["police", "thief"], required=True)
    peer_cmd.add_argument("--config-root", type=Path, default=Path("config"))
    peer_cmd.add_argument(
        "--series", action="store_true",
        help="Play the full network_and_league.num_games series against the same opponent "
             "(Appendix F Table 18), alternating role each sub-game, instead of one game.",
    )

    replay_cmd = sub.add_parser("replay", help="Replay and cryptographically verify a saved log.")
    replay_cmd.add_argument("--log", type=Path, required=True)

    report_cmd = sub.add_parser(
        "report", help="Email (or, by default, locally draft) the Sec. 9.3 report artifacts.",
    )
    report_cmd.add_argument("--role", choices=["police", "thief"], required=True)
    report_cmd.add_argument("--config-root", type=Path, default=Path("config"))
    report_cmd.add_argument(
        "--game-id", default=None,
        help="Override the auto-derived game_id (defaults to the one this role's own config "
             "would compute for the current series).",
    )

    args = parser.parse_args()

    if args.command == "peer":
        if args.series:
            run_peer_series(args.role, args.config_root)
        else:
            run_peer(args.role, args.config_root)
    elif args.command == "replay":
        run_replay(args.log)
    elif args.command == "report":
        run_report(args.role, args.config_root, args.game_id)


if __name__ == "__main__":
    main()
