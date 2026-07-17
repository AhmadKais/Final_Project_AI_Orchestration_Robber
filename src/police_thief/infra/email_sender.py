"""Gmail API reporting via OAuth 2.0, send-only scope (Appendix A, Sec. 9.3).

Attaches the four mandatory JSON report types (declaration, configuration,
log, results) and either sends them for real or writes a local preview,
depending on `[email] mode` in config/<role>/game.toml:

- mode = "send": a real, immediate, IRREVERSIBLE Gmail send via
  `send_report`, gated through the Gatekeeper (infra/gatekeeper.py) so a
  runaway loop can't spam the recipient.
- mode = "draft" (the default, and what any unrecognized value falls back
  to -- fails closed): `save_local_draft` writes the exact MIME message to
  a local .eml file next to the report and touches the Gmail API not at
  all. This is deliberately a LOCAL file, not a Gmail-side draft: creating
  a real Gmail draft needs the `gmail.compose`/`gmail.modify` scope, which
  this project does not request (least-privilege: `gmail.send` is enough
  for the one real action -- sending -- this module ever performs). Review
  the .eml, then flip to `mode = "send"` once ready to actually email it.

Requires credentials.json + token.json (both gitignored, never committed --
Appendix E rules 39-40) only for `mode = "send"`; local drafting needs
neither.
"""

from __future__ import annotations

import base64
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from police_thief.infra.gatekeeper import Gatekeeper

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def get_service(token_path: Path = Path("token.json"), credentials_path: Path = Path("credentials.json")):
    """Load/refresh OAuth credentials and build the Gmail API service.

    On first run (no token.json yet), runs the InstalledAppFlow consent
    flow using credentials_path and persists the resulting token so
    subsequent runs need no further interaction (Appendix A).
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _build_message(to_addr: str, subject: str, json_path: Path) -> str:
    json_path = Path(json_path)
    message = MIMEMultipart()
    message["to"] = to_addr
    message["subject"] = subject
    message.attach(MIMEText(f"Automated report attached: {json_path.name}"))

    attachment = MIMEApplication(json_path.read_bytes(), _subtype="json")
    attachment.add_header("Content-Disposition", "attachment", filename=json_path.name)
    message.attach(attachment)

    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def send_report(service, to_addr: str, subject: str, json_path: Path) -> dict:
    """Attach and SEND (irreversibly, immediately) one of the four
    mandatory JSON report files (declaration/configuration/log/results,
    Sec. 9.3.3)."""
    raw = _build_message(to_addr, subject, json_path)
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def _local_draft_path(json_path: Path) -> Path:
    json_path = Path(json_path)
    return json_path.with_name(f"draft_{json_path.stem}.eml")


def save_local_draft(to_addr: str, subject: str, json_path: Path) -> Path:
    """Write the exact MIME message `send_report` would send to a local
    .eml file next to the report, WITHOUT calling the Gmail API at all --
    no credentials, no network, nothing to revoke if it's wrong. This is
    the safe default (`[email] mode = "draft"`, or anything other than the
    exact string "send"). Returns the .eml path."""
    raw = _build_message(to_addr, subject, json_path)
    draft_path = _local_draft_path(json_path)
    draft_path.write_bytes(base64.urlsafe_b64decode(raw.encode("ascii")))
    return draft_path


def send_or_draft_report(
    service, gatekeeper: Gatekeeper, mode: str, to_addr: str, subject: str, json_path: Path,
) -> dict | Path:
    """Dispatch on `[email] mode`. "send" routes the real Gmail call
    through `gatekeeper.try_send` (Sec. 9.3.1-9.3.2: Quota -> TokenBucket
    -> DOSDetector) and raises if any gate blocks it -- a block here means
    something is actually wrong (quota exhausted, burst detected), not a
    normal outcome to swallow silently. Anything else, including the
    default "draft", writes a local .eml and never touches the gate or the
    network -- fails closed toward the safer option."""
    if mode == "send":
        result = gatekeeper.try_send(send_report, service, to_addr, subject, json_path)
        if result is None:
            raise RuntimeError(
                f"Gatekeeper blocked sending {Path(json_path).name} "
                "(daily quota, rate limit, or burst guard tripped)"
            )
        return result
    return save_local_draft(to_addr, subject, json_path)
