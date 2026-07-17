# Gmail API / OAuth 2.0 Setup (Appendix A)

> **Done and verified for real.** Steps A-E below were completed (Cloud project, consent screen, `gmail.send`-only scope, `credentials.json`, `token.json`) and confirmed end-to-end: `get_service()` reused `token.json` without re-prompting (proves the refresh token works for long-term autonomy), and `send_report()` sent a real email with a real Gmail message ID, carrying an actual sample report attachment. Kept below as a reference for anyone re-running this setup (e.g. after rotating credentials, or setting up the second team's repo).

## The five steps (spec Appendix A Sec. 1), in order

Skipping a step -- especially the consent screen -- makes the failure show up later and more confusingly, not immediately.

### A. Open a project and enable the Gmail API

Go to [Google Cloud Console](https://console.cloud.google.com/), create a new project (or pick an existing one), then in the API Library explicitly enable the **Gmail API**.

### B. Configure the OAuth consent screen

Choose **External** (unless you have a Google Workspace org, then Internal). Add your own email (and your teammate's) to the **Test users** list -- while the app is in Testing mode, only listed users can complete the auth flow.

### C. Restrict the scope to the minimum

Request only:

```
https://www.googleapis.com/auth/gmail.send
```

Never `gmail.modify` or `mail.google.com` -- least privilege means a leaked token can only send, never read or delete. `infra/email_sender.py`'s `SCOPES` constant already matches this exactly; nothing to change in code.

### D. Create credentials

On the Credentials page: **Create Credentials → OAuth Client ID → Application type: Desktop app**. Download the resulting file and save it as `credentials.json` **at the project root** (same directory as `pyproject.toml`) -- that's the default path `infra/email_sender.get_service()` looks for.

**Before anything else, confirm `.gitignore` covers it** (it already does — `credentials.json` and `token.json` are both listed):

```bash
git check-ignore -v credentials.json token.json
```

### E. First run creates `token.json`

The first time `get_service()` runs with no `token.json` present, it opens a browser for you to approve the consent screen, then writes `token.json` next to `credentials.json`. After that, every future run reuses and auto-refreshes it -- no repeated manual login.

```python
from pathlib import Path
from police_thief.infra.email_sender import get_service, send_report

service = get_service()  # first call: opens a browser, writes token.json
send_report(service, "rmisegal+uoh26finalgame@gmail.com", "Test", Path("docs/sample_reports/result_demo-001.json"))
```

## Sending the mandatory report artifacts (the wired-up CLI path)

`send_report`/`get_service` above are the low-level building blocks; the actual entry point a real match uses is:

```bash
uv run python -m police_thief report --role police
```

This finds every Sec. 9.3 artifact `SeriesRunner` already wrote for the current series (declaration, one config snapshot per sub-game, one log per sub-game, the final results file) and, per artifact, either sends it for real or writes a local preview -- controlled by `[email] mode` in `config/<role>/game.toml`:

- **`mode = "draft"` (the default, and what any typo/unrecognized value falls back to -- fails closed):** writes `draft_<artifact>.eml` next to each artifact in `logs/`. Nothing is sent, no Gmail API call is made at all, and `credentials.json`/`token.json` aren't even read. Open the `.eml` in any text editor (or an email client that can import raw MIME) to see exactly what would go out.
- **`mode = "send"`:** performs a real, immediate, irreversible send for each artifact, routed through the `Gatekeeper` (`infra/gatekeeper.py`, sized from `config/game.json`'s `rate_limiter_gatekeeper` section) so a bug can't spam the recipient -- a blocked gate raises rather than failing silently.

Recommended flow: leave `mode = "draft"` until you've reviewed the `.eml` files from a real series, then flip to `mode = "send"` and re-run the same command once you're ready for the real email to actually go out.

## Required files (Table 5)

| File | Source | Sensitivity |
|---|---|---|
| `credentials.json` | Downloaded in Step D | Secret -- gitignored |
| `token.json` | Auto-created in Step E | Secret -- gitignored |

**If either is ever committed, deleting it in a later commit is not enough** -- it's still in the git history. Rotate the credentials in the Cloud Console instead.

## What's done

| Item | Status |
|---|---|
| `get_service()`/`send_report()` implemented exactly per Appendix A's reference flow | Done |
| `send_report()` fully tested against a mocked Gmail service (`tests/test_email_sender.py`) | Done |
| `.gitignore` excludes both secret files | Done -- confirmed via `git check-ignore -v` |
| `Gatekeeper` (quota/rate-limit/DOS protection) wraps every real send | Done -- wired into the actual `mode = "send"` call path (`simulation_sdk.run_report` -> `email_sender.send_or_draft_report`), not just unit-tested in isolation |
| A CLI entry point (`police_thief report --role <role>`) that finds and reports every real Sec. 9.3 artifact for the current series, safe-by-default (`mode = "draft"` writes local `.eml` previews, no network) | Done |
| Cloud project, consent screen, `gmail.send`-only scope, `credentials.json` (Steps A-D) | Done (by the user -- a real account signup, not something that can be automated) |
| First-auth browser consent, `token.json` created (Step E) | Done |
| A real email actually sent and received, with a real Gmail message ID | Done -- verified, not just configured |

## Status

Fully working, and now actually wired to the CLI (`police_thief report`) rather than only callable by hand. Marked complete in `docs/TODO.md`. The remaining Gmail-related submission items: (1) switch `[email] recipient` in each team's private `config/<role>/game.toml` to the real course address (`rmisegal+uoh26finalgame@gmail.com`) once actual league play starts -- the test above deliberately went to the user's own address instead, to avoid sending test traffic to the real instructor inbox; (2) leave `mode = "draft"` until a real series has actually been played and its artifacts reviewed, then flip to `mode = "send"` for the real submission run.
