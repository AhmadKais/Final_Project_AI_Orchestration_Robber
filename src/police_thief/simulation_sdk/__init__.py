"""Single business entry point (Appendix D): wires config -> Orchestrator ->
interface for one role, and exposes the replay/verification entry point.

This is the only module `__main__.py` should import from directly.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from police_thief.domain.scoring import aggregate_series, effective_role_for_subgame, record_sub_game
from police_thief.domain.strategy.brain_base import BrainBase
from police_thief.domain.strategy.minimax_brain import MinimaxBrain
from police_thief.infra.email_sender import get_service, send_or_draft_report
from police_thief.infra.gatekeeper import build_gatekeeper
from police_thief.infra.llm.base import LLMProvider
from police_thief.infra.llm.claude_api_provider import ClaudeAPIProvider
from police_thief.infra.llm.claude_cli_provider import ClaudeCLIProvider
from police_thief.infra.llm.ollama_provider import OllamaProvider
from police_thief.infra.llm.template_provider import TemplateProvider
from police_thief.infra.mcp_client import OpponentClient
from police_thief.infra.mcp_server import MoveMailbox, build_server
from police_thief.interface.replay_viewer import ReplayViewer
from police_thief.peer_runtime.orchestrator import Orchestrator
from police_thief.shared.config_manager import Role, derive_game_id, load_game_config

_PROVIDERS = {
    "template": TemplateProvider,
    "ollama": OllamaProvider,
    "claude_api": ClaudeAPIProvider,
    "claude_cli": ClaudeCLIProvider,
}


def _build_brain(role: Role, strategy_cfg: dict) -> BrainBase:
    """`[strategy] police_class`/`thief_class` points at `package.module:Class`
    (Appendix F Table 22); empty/absent runs the shipped MinimaxBrain (belief-
    space minimax search -- see `domain/strategy/minimax_brain.py`)."""
    class_path = strategy_cfg.get(f"{role}_class")
    if not class_path:
        return MinimaxBrain(role=role)
    module_path, _, class_name = class_path.partition(":")
    brain_cls = getattr(importlib.import_module(module_path), class_name)
    return brain_cls(role=role)


def _build_llm_provider(trash_talk_cfg: dict) -> LLMProvider:
    """`[trash_talk] provider` (Appendix F Table 21); defaults to the
    zero-token template provider."""
    provider_name = trash_talk_cfg.get("provider", "template")
    if provider_name not in _PROVIDERS:
        raise ValueError(f"Unknown trash_talk provider: {provider_name!r}")
    return _PROVIDERS[provider_name]()


def _current_git_commit() -> str:
    """Best-effort HEAD commit hash for the Step-0 declaration (Appendix E
    rule 53: "record the commit hash that was played"). Never fatal --
    falls back to "unknown" outside a git repo or if git isn't installed."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def build_peer(role: Role, config_root: Path = Path("config")) -> Orchestrator:
    """Load config, construct the brain (from [strategy] or HeuristicBrain
    default), and assemble a ready-to-run Orchestrator for this role."""
    game_config = load_game_config(role, config_root)
    values = game_config.values
    network_cfg = values.get("network", {})

    brain = _build_brain(role, values.get("strategy", {}))
    llm_provider = _build_llm_provider(values.get("trash_talk", {}))

    mailbox = MoveMailbox()
    mcp_server = build_server(f"police_thief-{role}", mailbox)
    mcp_client = OpponentClient(
        network_cfg["opponent_url"],
        response_timeout_sec=values.get("network_and_league", {}).get("response_timeout_sec", 30),
    )

    from police_thief.shared.version import __version__

    game_cfg = values.get("game", {})
    llm_cfg = values.get("llm", {})

    orchestrator = Orchestrator(
        role=role, brain=brain, mcp_client=mcp_client, mailbox=mailbox,
        llm_provider=llm_provider, config=values,
        log_path=Path("logs") / f"{role}_match.json",
        code_version=__version__,
        github_commit=_current_git_commit(),
        group_name=game_cfg.get("group_name"),
        llm_model=llm_cfg.get("model", "unknown"),
    )
    # Stashed for run_peer, which alone needs to bind the server; nothing
    # else in Orchestrator's own API depends on these.
    orchestrator._mcp_server = mcp_server
    orchestrator._my_port = network_cfg["my_port"]
    return orchestrator


@dataclass
class SeriesRunner:
    """Owns everything that persists across a whole series (Appendix F
    Table 18: "Games in a series against one opponent" = 6, Fixed) -- the
    network connection, the LLM provider, shared identity fields -- and
    builds a fresh Orchestrator (fresh Board, BeliefMap, ScentField, log
    path) for each sub-game, alternating this peer's effective role
    (`domain.scoring.effective_role_for_subgame`). Never touches
    Orchestrator's own turn logic; only sequences multiple instances of
    its existing, already-tested single-game API, so the well-tested
    single-sub-game path (`build_peer`/`run_peer`) is untouched and stays
    available on its own."""

    config_natural_role: Role
    values: dict
    mailbox: MoveMailbox
    mcp_client: OpponentClient
    llm_provider: LLMProvider
    log_dir: Path
    game_id: str
    code_version: str
    github_commit: str
    group_name: str | None
    llm_model: str
    # Real identity data for the [Declaration File] (Sec. 9.3) beyond what
    # the game itself already produces (hardware from the real Step-0
    # exchange, group_name, code_version, github_commit) -- optional
    # because only the user knows their own team roster and repo URL.
    # Left empty, the declaration is still written with everything that
    # doesn't need that data, just with those two fields blank rather than
    # the file not existing at all.
    team_members: list[str] = field(default_factory=list)
    repo_url: str = ""

    async def run(self) -> dict:
        """Play every sub-game in sequence and write all four per-series
        JSON artifacts (Sec. 9.3): a [Declaration File] once (from
        sub-game 1's real Step-0 exchange), one [Configuration File] per
        sub-game (the actual shared config that sub-game ran under), each
        sub-game's own [Log File] (via Orchestrator, unchanged), and the
        aggregated [Results File] at the end ("each team's score in each
        mini-game and the cumulative result"). Returns the results payload
        for callers that want it directly (e.g. tests) without re-reading
        the file."""
        num_games = self.values.get("network_and_league", {}).get("num_games", 1)
        strategy_cfg = self.values.get("strategy", {})
        self.log_dir.mkdir(parents=True, exist_ok=True)
        sub_games = []
        first_orchestrator: Orchestrator | None = None
        for sub_game_number in range(1, num_games + 1):
            role = effective_role_for_subgame(self.config_natural_role, sub_game_number)
            brain = _build_brain(role, strategy_cfg)
            log_path = self.log_dir / f"log_{self.game_id}_g{sub_game_number:02d}.json"
            orchestrator = Orchestrator(
                role=role, brain=brain, mcp_client=self.mcp_client, mailbox=self.mailbox,
                llm_provider=self.llm_provider, config=self.values, log_path=log_path,
                code_version=self.code_version, github_commit=self.github_commit,
                group_name=self.group_name, llm_model=self.llm_model,
            )
            outcome = await orchestrator.run_game()
            first_orchestrator = first_orchestrator or orchestrator
            sub_games.append(record_sub_game(sub_game_number, role, outcome, self.values["scoring"]))
            self._write_config_snapshot(sub_game_number)
            self._drain_stale_messages()

        if first_orchestrator is not None:
            self._write_declaration(first_orchestrator)

        result = aggregate_series(sub_games, tie_score=self.values["scoring"]["tie_score"])
        payload = {
            "game_id": self.game_id,
            "my_total": result.my_total, "opponent_total": result.opponent_total,
            "winner": result.winner,
            "sub_games": [asdict(record) for record in result.sub_games],
        }
        (self.log_dir / f"result_{self.game_id}.json").write_text(json.dumps(payload, indent=2))
        return payload

    def _write_declaration(self, first_orchestrator: Orchestrator) -> None:
        """[Declaration File] (Sec. 9.3): constant data for the whole
        series -- both sides' identity, hardware, and MCP address, fixed
        with a signature. Hardware comes straight from sub-game 1's real
        Step-0 exchange (Sec. 5.5), not re-collected here; the exchange
        already happened as part of run_game()."""
        opponent_role = "thief" if self.config_natural_role == "police" else "police"
        declaration = {
            "game_id": self.game_id,
            "num_games": self.values.get("network_and_league", {}).get("num_games", 1),
            "teams": {
                self.config_natural_role: {
                    "group_name": self.group_name, "members": self.team_members, "repo": self.repo_url,
                },
                opponent_role: {"group_name": None, "members": [], "repo": None},  # opponent fills in their own
            },
            "hardware": {
                self.config_natural_role: asdict(first_orchestrator.own_step0) if first_orchestrator.own_step0 else None,
                opponent_role: first_orchestrator.opponent_step0,
            },
            "token_budget_per_series": self.values.get("network_and_league", {}).get("token_budget_per_series"),
        }
        (self.log_dir / f"declaration_{self.game_id}.json").write_text(json.dumps(declaration, indent=2))

    def _write_config_snapshot(self, sub_game_number: int) -> None:
        """[Configuration File] (Sec. 9.3): a per-sub-game named copy of
        the actual signed config that sub-game ran under ("every
        configuration file must be given a different name according to
        the game, so as to allow easy reconstruction of each game's
        configuration") -- byte-identical across sub-games here since
        nothing in `self.values` changes mid-series, but named separately
        per sub-game as the spec requires regardless."""
        config_path = self.log_dir / f"config_{self.game_id}_g{sub_game_number:02d}.json"
        config_path.write_text(json.dumps(self.values, indent=2, default=str))

    def _drain_stale_messages(self) -> None:
        """Discard anything left in the mailbox between sub-games -- a
        sub-game that ends via technical loss can leave a late message
        arriving after this side already stopped waiting for it, which
        would otherwise be misread as belonging to the NEXT sub-game."""
        for queue in (
            self.mailbox.moves, self.mailbox.commits, self.mailbox.acks, self.mailbox.reveals,
            self.mailbox.final_audits, self.mailbox.capture_claims, self.mailbox.step0s,
        ):
            while not queue.empty():
                queue.get_nowait()


def build_series(role: Role, config_root: Path = Path("config")) -> tuple[SeriesRunner, object, int]:
    """Like build_peer, but for a whole series: identical shared network/
    LLM construction, wrapped in a SeriesRunner instead of one
    Orchestrator. Returns (runner, mcp_server, my_port) -- run_peer_series
    binds the server; tests wire two runners' mcp_client/mailbox directly
    without a real port, the same in-process pattern
    test_orchestrator_integration.py already uses for single games."""
    game_config = load_game_config(role, config_root)
    values = game_config.values
    network_cfg = values.get("network", {})

    llm_provider = _build_llm_provider(values.get("trash_talk", {}))
    mailbox = MoveMailbox()
    mcp_server = build_server("police_thief-peer", mailbox)
    mcp_client = OpponentClient(
        network_cfg["opponent_url"],
        response_timeout_sec=values.get("network_and_league", {}).get("response_timeout_sec", 30),
    )

    from police_thief.shared.version import __version__

    game_cfg = values.get("game", {})
    llm_cfg = values.get("llm", {})
    # config/<role>/game.toml's [game] section already scaffolds `members`
    # and `repos = {cop, thief}` (this team's own two repo URLs -- a team
    # submits both, Sec. 9.4). `repos` keys on the book's Cop/Robber
    # vocabulary, not this codebase's police/thief Role literal, hence the
    # lookup below rather than a plain `.get(role)`.
    repo_key = "cop" if role == "police" else "thief"

    runner = SeriesRunner(
        config_natural_role=role, values=values, mailbox=mailbox, mcp_client=mcp_client,
        llm_provider=llm_provider, log_dir=Path("logs"), game_id=derive_game_id(values),
        code_version=__version__, github_commit=_current_git_commit(),
        group_name=game_cfg.get("group_name"), llm_model=llm_cfg.get("model", "unknown"),
        team_members=game_cfg.get("members", []), repo_url=game_cfg.get("repos", {}).get(repo_key, ""),
    )
    return runner, mcp_server, network_cfg["my_port"]


async def _run_peer_series_async(runner: SeriesRunner, mcp_server, my_port: int) -> None:
    server_task = asyncio.create_task(
        mcp_server.run_async(transport="http", host="0.0.0.0", port=my_port)
    )
    await asyncio.sleep(0.5)  # let the server finish binding before the series starts
    try:
        result = await runner.run()
        print(f"Series over: {result['winner']} (me {result['my_total']} - opponent {result['opponent_total']})")
    finally:
        # The opponent's last receive_final_audit call may have queued its
        # payload (satisfying our await) a moment before its own handler
        # coroutine gets scheduled again to flush the HTTP response --
        # cancelling the server immediately would kill that in-flight
        # response and time out the opponent's client (found by running two
        # real separate peer processes to a real game-over).
        await asyncio.sleep(1.0)
        server_task.cancel()


def run_peer_series(role: Role, config_root: Path = Path("config")) -> None:
    """Real network deployment for a full series (Appendix F Table 18):
    binds this role's server once and plays `network_and_league.num_games`
    sub-games against the same opponent, alternating this peer's effective
    role each sub-game. Needs a second real peer process to actually
    complete a series -- same caveat as run_peer. The series-runner
    machinery itself is fully covered in-process by
    tests/test_series_runner.py."""
    runner, mcp_server, my_port = build_series(role, config_root)
    asyncio.run(_run_peer_series_async(runner, mcp_server, my_port))


async def _run_peer_async(orchestrator: Orchestrator) -> None:
    server_task = asyncio.create_task(
        orchestrator._mcp_server.run_async(transport="http", host="0.0.0.0", port=orchestrator._my_port)
    )
    await asyncio.sleep(0.5)  # let the server finish binding before the game loop starts
    try:
        outcome = await orchestrator.run_game()
        print(f"Game over: {outcome.value}")
    finally:
        # Same shutdown race as _run_peer_series_async above: give the
        # opponent's final-audit handler time to flush its response before
        # this side tears its own server down.
        await asyncio.sleep(1.0)
        server_task.cancel()


def run_peer(role: Role, config_root: Path = Path("config")) -> None:
    """Real network deployment: binds this role's server and runs the game
    loop against config/<role>/game.toml's [network] opponent_url. Needs a
    second real peer process to actually complete a game -- not something
    this repo's own test suite can exercise (see docs/TUNNELING.md's same
    caveat for Stage 5); the Orchestrator this builds is fully covered by
    tests/test_orchestrator_integration.py using an in-process transport.
    """
    orchestrator = build_peer(role, config_root)
    asyncio.run(_run_peer_async(orchestrator))


def run_replay(log_path: Path) -> None:
    """Launch the replay viewer against a saved game log for cryptographic
    re-verification (Sec. 7.4-7.5)."""
    ReplayViewer(log_path).step_through()


def find_report_artifacts(log_dir: Path, game_id: str) -> list[Path]:
    """Locate this series' four mandatory JSON artifacts (Sec. 9.3) that
    SeriesRunner already wrote to `log_dir`: the declaration (once), every
    per-sub-game configuration snapshot, every per-sub-game log, and the
    final results file -- in that reading order. Silently skips any that
    don't exist yet (e.g. the series is still in progress, or ran as a
    single game via run_peer rather than run_peer_series)."""
    candidates = [
        log_dir / f"declaration_{game_id}.json",
        *sorted(log_dir.glob(f"config_{game_id}_g*.json")),
        *sorted(log_dir.glob(f"log_{game_id}_g*.json")),
        log_dir / f"result_{game_id}.json",
    ]
    return [path for path in candidates if path.exists()]


def run_report(role: Role, config_root: Path = Path("config"), game_id: str | None = None) -> list[tuple[Path, dict | Path]]:
    """Email (or, by default, locally draft) every report artifact this
    role's series has written so far. Reads `[email] recipient`/`mode`
    from config/<role>/game.toml -- `mode = "send"` performs a real,
    irreversible Gmail send per artifact, gated through the Gatekeeper
    built from config/game.json's `rate_limiter_gatekeeper`; any other
    mode (the default, "draft") writes local .eml previews and never
    touches the network or needs credentials.json/token.json at all.
    Returns a list of (artifact_path, outcome) pairs -- outcome is the
    Gmail API response dict for a real send, or the local .eml Path for a
    draft."""
    game_config = load_game_config(role, config_root)
    values = game_config.values
    email_cfg = values.get("email", {})
    to_addr = email_cfg.get("recipient")
    if not to_addr:
        raise ValueError(f"config/{role}/game.toml is missing [email] recipient")
    mode = email_cfg.get("mode", "draft")

    gid = game_id or derive_game_id(values)
    log_dir = Path("logs")
    artifacts = find_report_artifacts(log_dir, gid)
    if not artifacts:
        raise FileNotFoundError(f"No report artifacts found for game_id={gid!r} in {log_dir}")

    gatekeeper = build_gatekeeper(values["rate_limiter_gatekeeper"])
    service = get_service() if mode == "send" else None

    results = []
    for path in artifacts:
        subject = f"[police_thief] {path.stem} ({gid})"
        outcome = send_or_draft_report(service, gatekeeper, mode, to_addr, subject, path)
        verb = "Sent" if mode == "send" else "Drafted locally"
        print(f"{verb}: {path.name} -> {outcome if isinstance(outcome, Path) else 'sent'}")
        results.append((path, outcome))
    return results
