"""Gmail send-only reporting (Sec. 9.3, Appendix A). No real credentials or
network access is used or required -- the Gmail service is mocked
throughout, which is the standard way to test this kind of integration
code. Real end-to-end sending needs your own credentials.json/token.json
(Appendix A) and is out of scope for an automated test suite.
"""

import base64
import email
import json
from pathlib import Path
from unittest.mock import MagicMock

from police_thief.infra.email_sender import SCOPES, save_local_draft, send_or_draft_report, send_report
from police_thief.infra.gatekeeper import DOSDetector, Gatekeeper, QuotaManager, TokenBucket


def test_scopes_is_send_only():
    # Least-privilege: never request read/modify access to the mailbox.
    assert SCOPES == ["https://www.googleapis.com/auth/gmail.send"]


def test_send_report_calls_gmail_send_with_correct_user_id(tmp_path):
    report_path = tmp_path / "result_game1.json"
    report_path.write_text(json.dumps({"cop_score": 20, "thief_score": 5}))

    service = MagicMock()
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "msg123"
    }

    result = send_report(service, "grader@example.com", "Game result", report_path)

    assert result == {"id": "msg123"}
    service.users.return_value.messages.return_value.send.assert_called_once()
    _, kwargs = service.users.return_value.messages.return_value.send.call_args
    assert kwargs["userId"] == "me"
    assert "raw" in kwargs["body"]


def test_send_report_attaches_the_json_file_content(tmp_path):
    report_path = tmp_path / "result_game1.json"
    payload = {"cop_score": 20, "thief_score": 5}
    report_path.write_text(json.dumps(payload))

    service = MagicMock()
    send_report(service, "grader@example.com", "Game result", report_path)

    _, kwargs = service.users.return_value.messages.return_value.send.call_args
    raw_message = base64.urlsafe_b64decode(kwargs["body"]["raw"]).decode("utf-8", errors="ignore")

    assert "result_game1.json" in raw_message
    assert "grader@example.com" in raw_message
    assert "Game result" in raw_message


def test_send_report_encodes_attachment_bytes_faithfully(tmp_path):
    report_path = tmp_path / "log_game1.json"
    original_bytes = json.dumps({"steps": [1, 2, 3]}).encode("utf-8")
    report_path.write_bytes(original_bytes)

    service = MagicMock()
    send_report(service, "grader@example.com", "Log", report_path)

    _, kwargs = service.users.return_value.messages.return_value.send.call_args
    raw_message_bytes = base64.urlsafe_b64decode(kwargs["body"]["raw"])
    parsed = email.message_from_bytes(raw_message_bytes)

    attachment_part = next(
        part for part in parsed.walk() if part.get_filename() == "log_game1.json"
    )
    assert attachment_part.get_payload(decode=True) == original_bytes


# -- save_local_draft / send_or_draft_report ---------------------------------


def _gatekeeper() -> Gatekeeper:
    return Gatekeeper(
        quota=QuotaManager(daily_limit=100),
        bucket=TokenBucket(capacity=30, refill_rate=0.5),
        dos=DOSDetector(max_sends=30, window_sec=60),
    )


def test_save_local_draft_never_touches_the_network(tmp_path):
    report_path = tmp_path / "result_game1.json"
    report_path.write_text(json.dumps({"cop_score": 20, "thief_score": 5}))

    draft_path = save_local_draft("grader@example.com", "Game result", report_path)

    assert draft_path == tmp_path / "draft_result_game1.eml"
    assert draft_path.exists()
    raw_message = draft_path.read_bytes().decode("utf-8", errors="ignore")
    assert "result_game1.json" in raw_message
    assert "grader@example.com" in raw_message
    assert "Game result" in raw_message


def test_send_or_draft_report_defaults_to_local_draft_and_skips_the_gate(tmp_path):
    report_path = tmp_path / "result_game1.json"
    report_path.write_text(json.dumps({"cop_score": 20, "thief_score": 5}))
    gatekeeper = _gatekeeper()

    outcome = send_or_draft_report(
        service=None, gatekeeper=gatekeeper, mode="draft",
        to_addr="grader@example.com", subject="Game result", json_path=report_path,
    )

    assert outcome == tmp_path / "draft_result_game1.eml"
    assert outcome.exists()
    assert gatekeeper._recent_sends == []  # draft mode never consumes a gate slot


def test_send_or_draft_report_unrecognized_mode_fails_closed_to_draft(tmp_path):
    report_path = tmp_path / "result_game1.json"
    report_path.write_text("{}")
    gatekeeper = _gatekeeper()

    outcome = send_or_draft_report(
        service=None, gatekeeper=gatekeeper, mode="typo-mode",
        to_addr="grader@example.com", subject="Game result", json_path=report_path,
    )

    assert outcome.exists()


def test_send_or_draft_report_send_mode_routes_through_the_gatekeeper(tmp_path):
    report_path = tmp_path / "result_game1.json"
    report_path.write_text("{}")
    service = MagicMock()
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "msg123"
    }
    gatekeeper = _gatekeeper()

    outcome = send_or_draft_report(
        service=service, gatekeeper=gatekeeper, mode="send",
        to_addr="grader@example.com", subject="Game result", json_path=report_path,
    )

    assert outcome == {"id": "msg123"}
    service.users.return_value.messages.return_value.send.assert_called_once()
    assert len(gatekeeper._recent_sends) == 1


def test_send_or_draft_report_send_mode_raises_when_the_gate_blocks():
    gatekeeper = Gatekeeper(
        quota=QuotaManager(daily_limit=0),  # already exhausted
        bucket=TokenBucket(capacity=30, refill_rate=0.5),
        dos=DOSDetector(max_sends=30, window_sec=60),
    )
    service = MagicMock()

    try:
        send_or_draft_report(
            service=service, gatekeeper=gatekeeper, mode="send",
            to_addr="grader@example.com", subject="x", json_path=Path("unused.json"),
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
    service.users.return_value.messages.return_value.send.assert_not_called()
