# TODO

Mandatory repository content per spec Appendix E rule 50. Grouped by stage; see `docs/PRD/` for full acceptance criteria.

## Stage 1 — Base Logic ✅
- [x] Implement `Board.is_legal_move` / `apply_move` / `legal_moves` (`src/police_thief/domain/board.py`)
- [x] Implement barrier placement + capture detection (`Board.place_barrier`, `Board.is_capture`)
- [x] Implement `domain/rules.py` outcome determination
- [x] Implement `domain/scoring.py` payoff table
- [x] Un-skip and pass `tests/test_board.py` (+ new `test_rules.py`, `test_scoring.py`) -- 40/40 passing

## Stage 2 — Basic FastMCP Infrastructure ✅
- [x] Implement `infra/mcp_server.py` (`MoveMailbox`, `build_server`, `run_server`)
- [x] Implement `infra/mcp_client.py` (`OpponentClient.send_move`)
- [x] Manually verify: two local processes exchange a numeric move over localhost -- confirmed via real HTTP socket smoke test

## Stage 3 — Blind Strategy Module ✅
- [x] Implement `BrainBase.pick_move` legality wrapper
- [x] Implement `HeuristicBrain._pick_move` (full-information version, no belief yet)
- [x] Implement `BeliefMap.arg_max` / `.manhattan_distance` (the non-uncertainty half of belief.py)
- [x] Choose RL vs. heuristics vs. custom algorithm and document the choice -- pure heuristics (no RL), written up in README.md's "Academic report" §3

## Stage 4 — Language and Scent Integration ✅
- [x] Implement `ScentField.emit` / `.decay`
- [x] Implement `BeliefMap.update_from_scent` / `.update_from_hint` (`.arg_max` done in Stage 3)
- [x] Implement `TemplateProvider` (default, zero-token)
- [x] Implement `OllamaProvider`, `ClaudeAPIProvider`, `ClaudeCLIProvider` -- all mocked in tests (no real network/subprocess calls in the suite); `anthropic` added as a real dependency
- [x] `HeuristicBrain` already belief-map-driven, no change needed (verified via `test_belief_updates.py`)

## Stage 5 — Cloud Exposure and Tunneling ⛔ blocked on a second machine only
- [x] ngrok binary downloaded to `tools/ngrok`, verified runnable
- [x] ngrok account created (by the user) and authtoken configured (`tools/ngrok.yml`, gitignored) -- verified with `tools/ngrok config check`
- [x] Real tunnel opened and a real move round-tripped through the actual public ngrok URL to this project's own FastMCP server -- confirmed live, then cleaned up
- [ ] Update `config/<role>/game.toml` `opponent_url` for remote play -- trivial once there's an actual opponent to point at
- [ ] Run one full round against a remote peer -- **the only remaining blocker: requires an actual second machine on a different network**

## Stage 6 — Security and Cryptography ✅
- [x] Implement `domain/crypto.commit` / `.verify` / `.audit_log`
- [x] Implement `domain/protocol.build_message` / `.parse_message`
- [x] Implement `shared/system_info.collect_step0_declaration` / `.sign_declaration`
- [x] Un-skip and pass `tests/test_crypto.py` -- 96/96 passing, zero skips

## Stage 7 — Reporting and Visualization Shell ✅ (Gmail done for real now; LiveGUI screenshot still needs a display)
- [x] Complete Gmail OAuth setup (`credentials.json`, `token.json` — both gitignored, confirmed untracked) -- real Cloud project + consent screen + `gmail.send`-only scope done by the user, verified with a real sent email (real Gmail message ID, token reused without re-prompting) -- see `docs/GMAIL_SETUP.md`
- [x] Implement `infra/gatekeeper.py` (QuotaManager, TokenBucket, DOSDetector)
- [x] Implement `infra/email_sender.py` (tested against a mocked Gmail service)
- [x] Implement `interface/live_gui.py` (belief heatmap, turn banner) -- pure logic tested; live Tkinter rendering untested, no display/`python3-tk` in this sandbox
- [x] Implement `interface/replay_viewer.py` (Verified OK / TAMPERED)
- [x] Generate the 4 sample JSON reports (declaration/config/log/results) -- `scripts/generate_sample_reports.py` plays a real match and writes them to `docs/sample_reports/`; the log passes `ReplayViewer.verify_all()`. This is illustrative sample data (same purpose as the book's own attached examples), not a real league submission -- that still needs `credentials.json`/`token.json` and an actual opponent.

## Stage 8 — Orchestrator Integration ✅
- [x] Implement `shared/config_manager.py` (load/merge/hash `game.json` + `game.toml`)
- [x] Extend `infra/mcp_{server,client}.py` with the full Commit-Reveal message surface (commit/ack/reveal/final-audit/capture-claim)
- [x] Implement `peer_runtime/{deadline_tracker,watchdog}.py`
- [x] Implement `peer_runtime/orchestrator.py` (full per-turn Commit→Ack→Reveal→Verify loop + end-of-game mutual audit)
- [x] Implement `simulation_sdk/__init__.py` (`build_peer`, `run_peer`, `run_replay`)
- [x] Fix `BeliefMap.arg_max()` (was raising on an empty map -- broke turn 0) and add `COMMITTING -> TECHNICAL_LOSS` to the state machine (Fig. 11 says every communication stage should reach it, `COMMITTING` was missing)
- [x] Two Orchestrators play a full game end-to-end in-process, log passes `ReplayViewer.verify_all()`

## Post-wiring strategy hardening ✅
- [x] Wire Cop barrier placement all the way through the Commit-Reveal protocol (`domain/protocol.encode_move`/`decode_move`) -- previously implemented at the Board level (Stage 1) but never actually reachable from a real turn
- [x] Fix a real self-trapping bug: `HeuristicBrain` could wall off its own only route to the target (Sec. 3.4's own warning) -- now checks a safe alternate route exists first
- [x] Add mobility-aware tie-break to the Robber's evasion (prefers the resulting cell with more future legal moves, avoids dead ends)
- [x] Fix a real stuck-belief bug found via multi-seed integration testing: `BeliefMap.decay_toward_uniform` prevents an old, highly-confident-but-stale belief from taking 10+ turns to correct
- [x] Download ngrok into `tools/` (gitignored), confirm the exact remaining blocker directly (`ERR_NGROK_4018`, needs a real account)
- [x] Implement `OllamaProvider`/`ClaudeAPIProvider`/`ClaudeCLIProvider` for real (previously stubbed)
- [x] Generate real sample JSON reports from an actual match (`scripts/generate_sample_reports.py`)
- [x] Wire Step-0 hardware declaration exchange into `run_game()` (Sec. 5.5, Appendix E rules 24 & 53) -- `collect_step0_declaration`/`sign_declaration` existed since Stage 6 but were never actually called during a real game; now exchanged before the first move via a new `receive_step0`/`send_step0` MCP tool, and recorded in the log
- [x] Wire the Watchdog into `run_game()` (Sec. 8.4.2) -- also implemented-but-unused since Stage 8; `HeartbeatWatchdog` now runs on a real background OS thread (not another asyncio task in the same event loop, which a CPU-bound freeze would starve too) and the main loop checks it every turn
- [x] 182 tests, 181 passing, 1 skipped (no display/`tkinter`)

## Competitive strategy hardening ✅
- [x] Investigated the lecturer-provided reference simulator (`github.com/rmisegal/Game-P2P-Cop-Chase`) for wire compatibility -- its own README settles the question: it's an explicitly-basic "learning aid, not a submission skeleton," and "where this repo differs from the book, the book and its binding parameter table win." The book itself states the wire contract is set by live per-pair negotiation, not a fixed universal protocol -- confirmed our `crypto.py`/`scent.py` already follow the book's own literal formulas where the reference repo deviates (nonce placement, decay shape). No rewrite needed.
- [x] Implemented `domain/strategy/search.py` + `MinimaxBrain` -- belief-space-weighted bounded-depth minimax (worst-case-adversary search, not a fixed opponent model), now the SDK's default brain in place of the plain one-ply `HeuristicBrain`
- [x] Added `tests/support/local_sim.py` + `tests/test_strategy_adversarial.py` -- a local (non-networked) full-game simulator running statistical win-rate trials against a `RandomBrain` baseline, a `GreedyBrain` that reproduces the reference repo's own shipped policy, and `HeuristicBrain` itself, across randomized start positions
- [x] The adversarial harness caught two real bugs on its first run (not present in the old hand-picked unit tests, which only ever used a 100%-confident correct belief): (1) minimax had no time-preference -- a capture found this turn and one found three turns later both scored a flat +1000, so the search could stall indefinitely instead of closing a sure capture now; fixed with a depth-based speed bonus. (2) A stale, over-confident belief (built from several early scent deposits stacking on one cell before the opponent moved on) could coincide with the mover's own current cell, which the search treated as a live hypothesis even though `Board.is_capture()` on real positions had already ruled it out that same turn; fixed by excluding the mover's own cell from `BeliefMap.arg_max`/`.top_k`, and by decoupling belief-forgetting from the book-binding scent-decay rate (private per-peer tuning, not negotiated physics) so stale confidence fades faster.
- [x] 192 tests, 191 passing, 1 skipped (no display/`tkinter`)

## Simultaneous-move correctness + a second reference-repo comparison ✅
- [x] Compared against `github.com/AliTrabeh/dual-agent-race-mcp` (a different assignment -- 5x5 "race" variant, NL-only belief, one-way barriers -- so its exact rules don't transfer) and ported four genuinely portable ideas into `search.py`: BFS-based (barrier-aware) distance in place of raw Manhattan, a reachable-area "boxed-in" feature, move ordering for alpha-beta efficiency, and a hard search deadline with graceful fallback to `HeuristicBrain` (previously the search had NO timeout at all).
- [x] A mirror-match stress test (`MinimaxBrain` vs itself) at the real default start (`config/game.json`'s `cop_start`/`thief_start`) surfaced a real structural bug: the search modeled the turn SEQUENTIALLY (my move, then the opponent reacts to it) when the real protocol is SIMULTANEOUS commit-reveal -- neither side ever sees the other's this-turn move first. Fixed by making the root-ply decision a proper maximin over the real move matrix (worst case across every move the opponent could simultaneously choose), keeping the cheaper alternating approximation only for deeper continuation plies.
- [x] Found and fixed two more belief-corruption bugs the fix exposed: (1) a belief candidate could sit on a cell that had since become barriered (belief only tracks scent, which doesn't know about barriers) -- the search treated "opponent standing on a barrier" as a live hypothesis, once measured worth ~750 points to a retreat move against an ~715-point actual capture opportunity; (2) widening the barrier-placement range to distance 1 (meant to help the standoff) crashed the game -- the only candidate at that range is ever the Cop's own occupied cell, and barriering your own cell makes `STAY` illegal from it forever. Both fixed (`BeliefMap.arg_max`/`.top_k` now take a set of excluded cells -- own position AND every barrier; barrier range reverted to its correct [2,3] window with self-barriering explicitly disallowed).
- [x] A controlled depth sweep (4/5/6/7 against `GreedyBrain`, holding everything else fixed) found search depth >= 5 collapses Cop win rate from ~93% to ~33% -- not gradual, an immediate cliff, reproduced live: at depth 6 the Cop found every approach angle toward an unmoving, cornered target scored within hundredths of `STAY` and froze for 26 straight turns. This is genuine minimax worst-case pessimism (assuming a perfectly optimal adversary for many more plies makes every option look equally futile), not a bug -- kept `_SEARCH_DEPTH = 4`, which retains the simultaneous-move fix without searching deep enough to talk itself into that paranoia.
- [x] Added independent per-instance tie-break jitter (`MinimaxBrain._TIE_BREAK_JITTER`) to reduce (not eliminate) the mirror-match standoff -- two byte-identical brains compute perfectly correlated responses, a known failure mode of pure-strategy play in symmetric simultaneous games. Calibrated small (0.05) after confirming a larger value (1.0) measurably overrode genuine move preferences against real (non-mirrored) opponents. Measured mirror-match resolution: ~80% across five starting geometries -- a real, honestly-documented floor (`test_mirror_match_resolves_more_often_than_not`), not a claim of guaranteed capture against an opponent that essentially never occurs in real play (no classmate runs byte-identical code).
- [x] Final measured win rates (25-30 game samples): Cop vs `GreedyBrain` Thief ~88%, Cop vs `RandomBrain` Thief ~85-87%, Thief vs `GreedyBrain` Cop ~64%, Thief vs `RandomBrain` Cop ~96%.
- [x] 196 tests, 195 passing, 1 skipped, full suite ~3.3 minutes.

## Submission checklist (Appendix C Table 6) — do last
- [x] Two GitHub repos (Cop, Robber), cross-linked READMEs -- local side done: `Final_Project` (Cop, existing `origin`) and a sibling full clone `../Final_Project_AI_Orchestration_Robber` (history preserved, `origin` remote removed pending its own real GitHub remote), each README cross-linking the other by URL. **Still needs the user**: create the actual `Final_Project_AI_Orchestration_Robber` GitHub repo and push both -- I don't have (and shouldn't have) push permission. See the exact commands below.
- [x] `v1.0-submission` annotated Git tag -- created locally in both repos, pointing at each one's latest commit. **Still needs the user**: `git push origin v1.0-submission` in each repo once its GitHub remote exists.
- [x] README report components complete in both repos (Sec. 9.4.2) -- items 1-4 and 6 (Dec-POMDP model, FastMCP dilemmas, strategies with real measured evidence, N/A learning curves, companion link) written for real in both READMEs; item 5 (screenshots) still needs a real display, which this environment doesn't have
- [ ] Belief-map and `Verified OK` replay screenshots attached -- **blocked, needs a real display** (`python3-tk`); `interface/live_gui.py`'s logic is implemented and tested, only the actual screenshot is outstanding
- [ ] At least 2 matches played against different teams -- **blocked, needs real classmate opponents**; cannot be done solo or simulated
- [ ] End-of-match email sent by both sides, separately -- depends on those real matches happening first
- [x] `.gitignore` verified — no secrets committed (`credentials.json`, `token.json`, `tools/ngrok.yml` all confirmed gitignored and untracked via `git status --short --ignored` / `git ls-files`)

### Exact remaining commands (run these yourself — I don't have GitHub push permission)

```bash
# 1. Create the second GitHub repo (public, or private + shared with the lecturer)
gh repo create AhmadKais/Final_Project_AI_Orchestration_Robber --public --source=/home/ahmadk/Desktop/AI_Orchestration_Course/Final_Project_AI_Orchestration_Robber --remote=origin
# (or create it on github.com and: cd ../Final_Project_AI_Orchestration_Robber && git remote add origin <url>)

# 2. Push the Robber repo
cd /home/ahmadk/Desktop/AI_Orchestration_Course/Final_Project_AI_Orchestration_Robber
git push -u origin main
git push origin v1.0-submission

# 3. Push the Cop repo's new commits + tag (existing origin, already set up)
cd /home/ahmadk/Desktop/AI_Orchestration_Course/Final_Project
git push origin main
git push origin v1.0-submission
```
