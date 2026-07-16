"""CLI entry point (Appendix D Sec. 3):

    uv run python -m police_thief peer --role police                # one game
    uv run python -m police_thief peer --role thief --series         # the real league format --
                                                                       # Appendix F Table 18's mandatory
                                                                       # 6-game series, role alternating
    uv run python -m police_thief replay --log logs/police_match.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from police_thief.simulation_sdk import run_peer, run_peer_series, run_replay


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

    args = parser.parse_args()

    if args.command == "peer":
        if args.series:
            run_peer_series(args.role, args.config_root)
        else:
            run_peer(args.role, args.config_root)
    elif args.command == "replay":
        run_replay(args.log)


if __name__ == "__main__":
    main()
