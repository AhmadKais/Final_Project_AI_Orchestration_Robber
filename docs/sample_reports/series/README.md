# Sample Series Report

A full **6-game league series** (Appendix F Table 18: "Games in a series
against one opponent" = 6, Fixed), generated from an **actual played
series** — not fabricated data — through the real `SeriesRunner`
(`simulation_sdk.py`), the same code real league play uses. Regenerate
anytime with:

```bash
uv run python scripts/generate_sample_series_report.py
```

Unlike `docs/sample_reports/`'s single-sub-game illustration (one
`[Log File]`/`[Configuration File]` pair), this shows the full per-series
artifact set as it's actually produced during real `--series` play:

| File (per side, in `police/` and `thief/`) | Count | Role (Sec. 9.3) |
|---|---|---|
| `declaration_<game_id>.json` | 1 | `[Declaration File]` — written once, from the real Step-0 exchange of sub-game 1 |
| `config_<game_id>_g<NN>.json` | 6 | `[Configuration File]` — one per sub-game, byte-identical here since nothing changes mid-series, named separately as the spec requires |
| `log_<game_id>_g<NN>.json` | 6 | `[Log File]` — one per sub-game, each independently `ReplayViewer(...).verify_all()`-checkable |
| `result_<game_id>.json` | 1 | `[Results File]` — every sub-game's outcome plus the cumulative score and series winner |

`game_id` (`group-a-group-b_<hash prefix>`) is computed identically by
both sides with zero extra negotiation, from data already in the signed
shared config (`shared/config_manager.derive_game_id`) — not hand-picked
for this sample.

Both sides ran the real default strategy (`MinimaxBrain`) with role
alternation across the series (odd sub-games: config-natural role; even:
opposite — `domain/scoring.effective_role_for_subgame`). The result is a
genuine, close, believable outcome (not staged to look impressive): both
teams are running identical logic, so this is effectively the mirror-match
scenario documented in the main README's "strategies implemented" section
— captures happen quickly in most sub-games, but the series is
competitive precisely because both sides are equally strong.

Team member IDs and repo URLs here are illustrative placeholders (matching
`docs/sample_reports/`'s existing convention) — real `--series` play
leaves those two `declaration` fields blank unless supplied via
`config/<role>/game.toml`'s `[game]` `members`/`repo_url` (optional; see
the main README's "Running" section).
