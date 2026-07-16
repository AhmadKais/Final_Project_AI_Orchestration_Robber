"""Single business entry point (Appendix D): wires config -> Orchestrator ->
interface for one role, and exposes the replay/verification entry point.

This is the only module `__main__.py` should import from directly.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from police_thief.domain.scoring import aggregate_series, effective_role_for_subgame, record_sub_game
from police_thief.domain.strategy.brain_base import BrainBase
from police_thief.domain.strategy.minimax_brain import MinimaxBrain
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

    async def run(self) -> dict:
        """Play every sub-game in sequence and write the aggregated
        [results file] (Sec. 9.3: `result_<game_id>.json`, "each team's
        score in each mini-game and the cumulative result"). Returns the
        same payload that gets written, for callers that want it directly
        (e.g. tests) without re-reading the file."""
        num_games = self.values.get("network_and_league", {}).get("num_games", 1)
        strategy_cfg = self.values.get("strategy", {})
        sub_games = []
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
            sub_games.append(record_sub_game(sub_game_number, role, outcome, self.values["scoring"]))
            self._drain_stale_messages()

        result = aggregate_series(sub_games, tie_score=self.values["scoring"]["tie_score"])
        payload = {
            "game_id": self.game_id,
            "my_total": result.my_total, "opponent_total": result.opponent_total,
            "winner": result.winner,
            "sub_games": [asdict(record) for record in result.sub_games],
        }
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / f"result_{self.game_id}.json").write_text(json.dumps(payload, indent=2))
        return payload

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

    runner = SeriesRunner(
        config_natural_role=role, values=values, mailbox=mailbox, mcp_client=mcp_client,
        llm_provider=llm_provider, log_dir=Path("logs"), game_id=derive_game_id(values),
        code_version=__version__, github_commit=_current_git_commit(),
        group_name=game_cfg.get("group_name"), llm_model=llm_cfg.get("model", "unknown"),
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
