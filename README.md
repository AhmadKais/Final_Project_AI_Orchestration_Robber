# Distributed Cops-and-Robbers over a Peer-to-Peer Network — Cop repository

**Companion repository (Robber): https://github.com/AhmadKais/Final_Project_AI_Orchestration_Robber**

Course final project for *Orchestration of AI Agents*, University of Haifa. Two symmetric autonomous agents — **Cop** and **Robber** — chase each other on a grid board with no central server: partial observability is modeled as a Dec-POMDP, location belief comes from a decaying scent-trail (stigmergy) mechanism cross-referenced against (possibly false) verbal hints, and fairness with no referee is enforced by a Commit-Reveal cryptographic protocol over SHA-256.

Per spec Sec. 9.4: both repositories hold the identical full codebase (the architecture is symmetric -- one binary, `--role police`/`--role thief` at the command line selects behavior) submitted as two separately-hosted, cross-linked repositories, matching how the two agents run as two genuinely separate processes/machines during real play.

Full translated specification: [`police_thief_p2p_EN.md`](police_thief_p2p_EN.md) (translated from the original Hebrew, [`police_thief_p2p.pdf`](police_thief_p2p.pdf)).

**Status: playable end-to-end, including the real 6-game league series format, and verified over the real public internet and real Gmail.** All 8 development stages (`docs/PLAN.md`) are implemented and tested, plus all four LLM providers, Step-0 hardware-declaration exchange, a real background-thread Watchdog, a belief-space minimax search strategy (`MinimaxBrain`, the default), and full `network_and_league.num_games`-series orchestration with role alternation and cumulative scoring (Appendix F Table 18 -- see "Running" below). Tunneling (Stage 5) and Gmail OAuth (Appendix A) are both genuinely done, not just coded: the user created real ngrok and Google Cloud accounts, and both were verified with live traffic, not just configuration -- a real move round-tripped through an actual public `*.ngrok-free.app` tunnel back to this project's own FastMCP server (`docs/TUNNELING.md`), and a real email (real Gmail message ID, with a sample report attached) was sent through the real Gmail API, with the refresh token confirmed working for unattended reuse (`docs/GMAIL_SETUP.md`). The only piece left anywhere is running an actual opponent on a second machine for real league play -- a hardware/logistics requirement no amount of local setup can substitute for. Two `Orchestrator`s (or two `SeriesRunner`s, for a full series) can play a complete, cryptographically-verified game against each other right now (proven by `tests/test_orchestrator_integration.py` and `tests/test_series_runner.py`, and by `scripts/generate_sample_reports.py`'s real generated match in `docs/sample_reports/`); real network deployment (`simulation_sdk.run_peer`/`run_peer_series`) uses the identical code path, just pointed at a real opponent URL instead of an in-process one -- confirmed by actually running two fully separate `police_thief peer` processes against each other over real localhost sockets (not the in-process test transport), which found and fixed a genuine connection-race bug neither the sandbox nor 214 in-process tests could ever have exercised (`docs/TUNNELING.md` has the full story). 230 tests, 229 passing, 1 skipped (no display/`tkinter` in the dev sandbox this was built in).

## Architecture

Mirrors the reference layout described in the spec's Appendix D:

```
interface/        Live GUI (belief heatmap, turn banner) + Replay Viewer
simulation_sdk/    Single business entry point: config -> Orchestrator -> interface
peer_runtime/      One independent peer: negotiation -> turn loop -> audit
  orchestrator.py    Single-gateway coordinator (Sec. 8.3)
  state_machine.py   Legal turn-phase transitions (Sec. 8.3, Fig. 11)
  deadline_tracker.py  Per-request timeout (Sec. 8.4.1)
  watchdog.py        Whole-loop heartbeat monitor (Sec. 8.4.2)
domain/            Pure game logic -- board, scent, belief, rules, scoring, crypto, protocol
  strategy/          Pluggable movement-policy "brain" (Chapter 6) -- YOUR extension point
infra/             External I/O -- FastMCP transport, LLM providers, Gmail sender, Gatekeeper
shared/            Config loading, Step-0 hardware declaration, versioning
```

The Cop's and Robber's code run as two fully separate processes, selected at launch by `--role` and reading from separate config directories (`config/police/` vs `config/thief/`). They **never share memory or import live state from each other** — that's a hard rule (spec Sec. 2.4.2, Appendix E rule 2), not a style preference.

## Configuration

- [`config/game.json`](config/game.json) — the shared, cryptographically-signed contract both peers must load byte-for-byte identically: board size, scoring, pheromone decay, rate limits, etc. Defaults here are the spec's binding minimums (Appendix F). Never hand-edit a number the spec expresses as a bracketed `[parameter]` anywhere else in the code.
- [`config/police/game.toml`](config/police/game.toml) / [`config/thief/game.toml`](config/thief/game.toml) — private, per-role settings (network port, opponent URL, strategy-class override, LLM mode, email). Not signed, not negotiated.

## Setup

```bash
uv sync
```

## Running

```bash
# One game:
# Terminal 1
uv run python -m police_thief peer --role police
# Terminal 2
uv run python -m police_thief peer --role thief

# The real league format instead -- a full network_and_league.num_games
# series against the same opponent (Appendix F Table 18: 6, Fixed),
# alternating this peer's effective role each sub-game, with cumulative
# scoring and a combined results file at the end:
uv run python -m police_thief peer --role police --series
uv run python -m police_thief peer --role thief --series

# Replay and cryptographically verify a saved match:
uv run python -m police_thief replay --log logs/police_match.json

# Email (or, by default, locally draft) the Sec. 9.3 report artifacts
# for the series you just played:
uv run python -m police_thief report --role police
```

Both peers need real, reachable `opponent_url`s in their `config/<role>/game.toml` -- `localhost` ports for same-machine testing, or public tunnel URLs for real league play (`docs/TUNNELING.md`).

**Multi-game series** (`--series`): writes all four Sec. 9.3 artifacts. Each sub-game gets its own `logs/log_<game_id>_g<NN>.json` and `logs/config_<game_id>_g<NN>.json`; once, from sub-game 1's real Step-0 exchange, `logs/declaration_<game_id>.json`; at the end, one `logs/result_<game_id>.json` summarizing every sub-game's outcome plus the cumulative score and winner. `game_id` is computed identically by both sides with no extra negotiation step, from data already in the signed shared config (the agreed team pair + the config's own hash) -- see `shared/config_manager.derive_game_id`. The declaration's team-member IDs and repo URL come from `config/<role>/game.toml`'s `[game]` `members`/`repos` -- fill in your real roster and the two repo links there before a real submission; left as the shipped `TODO-*` placeholders, those two fields are just blank in the declaration rather than fabricated.

**Reporting** (`report`): finds every artifact the series above just wrote and, per artifact, either emails it for real or writes a local preview -- controlled by `[email] mode` in `config/<role>/game.toml`. `mode = "draft"` (the shipped default, and what any unrecognized value falls back to) writes `logs/draft_<artifact>.eml` and never touches the Gmail API, so it needs no credentials at all; `mode = "send"` performs a real, irreversible send per artifact through the `Gatekeeper` (`infra/gatekeeper.py`, quota/rate-limit/DOS protection sized from `config/game.json`'s `rate_limiter_gatekeeper`). See `docs/GMAIL_SETUP.md` for full OAuth setup.

## Sample reports

Real, actually-played examples of every JSON artifact the spec requires (Sec. 9.3, Appendix F Table 20) -- generated by playing genuine matches through this project's own real code, never hand-written:

- [`docs/sample_reports/`](docs/sample_reports/) — one sub-game's four files (`scripts/generate_sample_reports.py`)
- [`docs/sample_reports/series/`](docs/sample_reports/series/) — a full real 6-game league series, both sides running the actual default strategy (`MinimaxBrain`) with role alternation (`scripts/generate_sample_series_report.py`)

## Development order

Built in the eight layered stages defined in [`docs/PLAN.md`](docs/PLAN.md) / [`docs/PRD/`](docs/PRD/) — each stage ran end-to-end before the next began (spec Chapter 10; Stage 8 is a courtesy addition that wires 1-7 into an actually-runnable game). See [`docs/TODO.md`](docs/TODO.md) for the current task breakdown and [`docs/STRATEGY.md`](docs/STRATEGY.md) for how to plug in your own movement-policy brain.

## Tests

```bash
uv run pytest
```

229 of 230 tests pass; the one skip is `test_live_gui.py`'s Tkinter widget-construction test, which needs a real display and `python3-tk` (not present in the sandbox this was built in — the pure heatmap/banner logic it depends on is fully tested). The centerpiece is `tests/test_orchestrator_integration.py`: two `Orchestrator`s, wired to each other's in-process FastMCP servers, play a complete game and produce a log that cryptographically re-verifies end to end. `tests/test_series_runner.py` does the same for a full multi-sub-game series (below). `tests/test_mcp_infra.py` additionally covers real connection-retry behavior (see `docs/TUNNELING.md`).

---

## Academic report (spec Sec. 9.4.2)

Mandatory content for the README of **each** of the two submission repositories (Cop and Robber, cross-linked). Items 1-4 and 6 are written for real below; item 5 needs a real display, which this environment doesn't have.

### 1. The chosen Dec-POMDP model

- **State** `S`: the objective board — `(cop_pos, thief_pos, barriers)`. Neither agent ever observes it directly; `Board` exists as each `Orchestrator`'s own reconstruction, kept accurate only because Commit-Reveal makes every revealed move truthful.
- **Observation** `Ω_i`: each agent's own position (exact), the *opponent's* `ScentField` (a decaying spatial signal built from the opponent's historical positions — never its current one), and the opponent's verbal hint (natural language, possibly false). `Ω_i` is a strict subset of `S` — this is what "local truth" means concretely.
- **Action** `A_i`: `{N, S, E, W, STAY}` for the Robber; the Cop additionally may fold a barrier placement into a `STAY` (`domain/protocol.encode_move`).
- **Transition** `P`: deterministic given both sides' *revealed* moves — no stochastic dynamics. All of this project's uncertainty lives on the observation side, not the transition side; adding transition noise on top of partial observability and adversarial deception would be uncertainty stacked on uncertainty with no way to isolate which one is driving a given loss.
- **Reward** `R`: the asymmetric scoring table (Table 2), paid once at episode end (capture / survival / technical loss) — sparse and terminal, not per-step. `γ` is therefore not meaningfully exercised within an episode.
- **Belief approximation**: exact joint Bayesian filtering over `S` is intractable at any real board size (Chapter 1's own point about exhaustive search). `BeliefMap` instead keeps an independent per-cell posterior, updated from two evidence channels (scent intensity, parsed verbal hint) with an explicit forgetting term (`decay_toward_uniform`) — a deliberate practical approximation, not exact POMDP solving, matching the spec's framing that heuristics (not exact inference) are the intended track.

### 2. FastMCP orchestration dilemmas

- **Queue management**: `MoveMailbox` gives every Commit-Reveal message *kind* its own `asyncio.Queue` (moves/commits/acks/reveals/final_audits/capture_claims/step0s) rather than one shared inbox. A single mixed queue was considered and rejected — both peers race independently through turn phases under `asyncio.gather`, and filtering a shared queue by tag would need fragile peek/requeue logic.
- **Network-failure handling**: every wait goes through `DeadlineTracker`, converting an unresponsive opponent into an explicit `TECHNICAL_LOSS` instead of an indefinite hang (Sec. 8.4.1's "a missed deadline is a failure, not patience").
- **Gatekeeper vs. Orchestrator — two different patterns for two different problems.** The Orchestrator is a single-gateway *coordinator* for the game's own internal subsystems (state machine, brain, log, deadline tracker, watchdog). The Gatekeeper is a rate-limiting *pipeline* guarding one external, quota-constrained resource (the Gmail API). Conflating them would be a mistake: the Orchestrator has no business knowing about Gmail quotas, and the Gatekeeper has no business knowing about game state.
- **Two bugs the wiring itself surfaced** (not visible from any single subsystem's own unit tests): `BeliefMap.arg_max()` raised on an empty map — fine in isolated Stage-3 tests, fatal on turn 0 of a real game, where no evidence exists yet. And the state machine was missing `COMMITTING -> TECHNICAL_LOSS`, even though a network failure can happen while awaiting an opponent's *ack*, not only during `AWAITING_REVEAL`.
- **Watchdog placement**: first considered as another `asyncio.Task` in the same event loop as the game coroutine — rejected, since a genuinely CPU-bound freeze in the main loop (e.g. a buggy custom strategy brain) would starve a same-loop task too, defeating the point of an "independent" monitor (Sec. 8.4.2). Implemented on a real background OS thread instead.

### 3. The strategies implemented

- **Movement (default)** — `MinimaxBrain` (`domain/strategy/search.py`), the game-theory track (Sec. 6.3): a bounded-depth (4-ply) minimax search over the belief map's top-3 weighted candidate opponent cells, modeling the opponent as a worst-case-competent adversary rather than a fixed weak model. The root decision is a proper maximin over the real *simultaneous* move matrix (every move I could make crossed with every move the opponent could simultaneously make from each believed cell) — the deeper continuation still uses cheaper alternating-turn minimax as an approximation, standard practice for bounding search cost. Falls back to `HeuristicBrain` (below) if a hard search deadline expires, so a slow decision never risks the opponent's own response timeout.
- **Movement (baseline)** — `HeuristicBrain`, the pure one-ply-lookahead heuristic (Sec. 6.3.1) `MinimaxBrain` extends: Cop minimizes Manhattan distance to `belief.arg_max()`; Robber maximizes it, tie-broken by which resulting cell keeps the most future legal moves open.
- **Barrier placement** — `HeuristicBrain` uses a hand-filtered heuristic: seal one of the target's orthogonal escape routes only when (a) within Manhattan distance 2-3 of the believed target, and (b) doing so provably leaves at least one other move that still makes progress (a real self-trapping bug found by integration testing — Sec. 3.4's own warning). `MinimaxBrain` instead evaluates *every* legal placement (its four orthogonal neighbors) through the same search used for movement and picks whichever, move or barrier, scores highest -- the search's own multi-ply worst-case lookahead already penalizes a self-trapping placement without a separate hand-coded check. This directly fixed a real underuse problem: traces with the narrower heuristic showed the Cop going 25+ turns with 13 barriers still unused because no candidate ever satisfied the narrow "must be reachable AND a target escape route" filter; with full-search evaluation the same mirror-match scenario resolved in 8-16 turns instead of 30+ or not at all (see below).
- **Belief** — an independent per-cell Bayesian posterior from the opponent's scent field (likelihood ∝ 1 + intensity) and their verbal hint (a deterministic direction-keyword parser — not an LLM, keeping spatial reasoning out of the language model's hands per Sec. 6.5), plus a decay-toward-uniform forgetting term (rate decoupled from the book-binding scent-decay rate, since belief-forgetting is private per-peer tuning, not negotiated physics). `BeliefMap.arg_max`/`.top_k` exclude the querying side's own current cell and every currently-barriered cell from consideration — both are physically impossible current-opponent-position hypotheses (if either were true, the real engine's own `Board.is_capture()` on ground-truth positions would already have ended the game), and treating either as live corrupted real decisions in testing (see below).
- **Verbal layer** — `TemplateProvider` (zero-token, default) produces flavor text structurally decoupled from the actual, cryptographically committed move. `OllamaProvider`/`ClaudeAPIProvider`/`ClaudeCLIProvider` are also fully implemented for real language-model bluffing, selectable via `[trash_talk] provider` with no code changes.
- **Why search over heuristics, and not RL**: the spec presents heuristics, an LLM-driven strategy, and RL as three equal-value tracks (Sec. 6.3), and states heuristics alone are fully competitive — but a plain one-ply heuristic is exploitable by any opponent with real lookahead. A bounded-depth adversarial search directly strengthens that same track without training infrastructure or a learning-curve requirement. `BrainBase` stays decoupled from any particular decision method, so a Q-Learning subclass (Bellman-equation update, epsilon-greedy exploration) could still be added later without touching the Orchestrator at all.
- **Empirical evidence** — `tests/support/local_sim.py` + `tests/test_strategy_adversarial.py` run statistical trials (25-30 games/matchup, seeded for reproducibility) directly against `Board`/`BeliefMap`/`ScentField`, bypassing only the commit-reveal transport layer (covered separately by `test_orchestrator_integration.py`). Measured: Cop (`MinimaxBrain`) beats a random Thief ~85-87% and a one-ply-greedy Thief (reproducing the lecturer-provided reference simulator's own shipped baseline) ~88%; Thief survives a random Cop ~96% and a greedy Cop ~64%. `MinimaxBrain` measurably outperforms `HeuristicBrain` in head-to-head comparison against the same greedy opponent in both roles.
- **A documented limit, not a claim of unbeatability** — a mirror-match stress test (`MinimaxBrain` vs. an independent instance of itself) found that two byte-identical, perfectly-correlated searches can lock into a stable adjacent-cell standoff neither side's search alone resolves, a known failure mode of deterministic pure-strategy play in symmetric simultaneous games. Independent per-instance tie-break randomization (`_TIE_BREAK_JITTER`) plus full-search barrier evaluation (above) together raise resolution to ~87% across five tested starting geometries, with captures converging in ~12 moves on average where they previously took 30+ or never resolved -- a real, honestly-measured floor for the single hardest opponent that could theoretically exist, not 100%, and one no real classmate's independently-built agent will actually be.
- **A cautionary finding on search depth** — a controlled sweep (depths 4-7 against the greedy baseline, everything else held fixed) found depth ≥ 5 collapses Cop win rate from ~93% to ~33%, reproduced live: at depth 6 the Cop found every approach angle toward an unmoving, cornered target scored within hundredths of a point of standing still, and froze for 26 straight turns. Deeper worst-case lookahead made every option look equally futile against an opponent nowhere near that strong — genuine minimax over-conservatism, not a defect in the search itself. Kept at depth 4.

### 4. Learning curves

N/A — no reinforcement learning was used (see above). A team adding a Q-Learning `BrainBase` subclass on top of this codebase would put its learning curves here.

### 5. Screenshots — still needed

Belief-map heatmap (Live GUI) and `Verified OK` (Replay App) screenshots need a real display and `python3-tk`, neither present in the sandbox this was built in. `interface/live_gui.py`'s rendering logic is implemented and its pure color/banner computation is tested (`tests/test_live_gui.py`); only the actual widget screenshot is outstanding.

### 6. Companion repository link

This is the **Cop** repository. Robber (identical codebase, separately hosted): **https://github.com/AhmadKais/Final_Project_AI_Orchestration_Robber**
