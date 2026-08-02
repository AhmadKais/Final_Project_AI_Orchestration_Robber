"""simulation_sdk.run_report / find_report_artifacts (Sec. 9.3 reporting).
No real credentials or network access -- `mode = "draft"` (the config
fixture's default) never calls get_service() at all, and the one
`mode = "send"` test mocks `get_service` instead of touching Gmail.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from police_thief.shared.config_manager import derive_game_id, load_game_config
from police_thief.simulation_sdk import find_report_artifacts, run_report


# -- find_report_artifacts ----------------------------------------------------

def test_find_report_artifacts_orders_declaration_configs_logs_result(tmp_path):
    gid = "abc123"
    names = [
        f"result_{gid}.json", f"log_{gid}_g02.json", f"config_{gid}_g01.json",
        f"declaration_{gid}.json", f"log_{gid}_g01.json", f"config_{gid}_g02.json",
    ]
    for name in names:
        (tmp_path / name).write_text("{}")

    found = find_report_artifacts(tmp_path, gid)

    assert [p.name for p in found] == [
        f"declaration_{gid}.json",
        f"config_{gid}_g01.json", f"config_{gid}_g02.json",
        f"log_{gid}_g01.json", f"log_{gid}_g02.json",
        f"result_{gid}.json",
    ]


def test_find_report_artifacts_skips_missing_files(tmp_path):
    gid = "abc123"
    (tmp_path / f"result_{gid}.json").write_text("{}")

    found = find_report_artifacts(tmp_path, gid)

    assert found == [tmp_path / f"result_{gid}.json"]


# -- run_report ---------------------------------------------------------------

SHARED_CONFIG = {
    "agreed_between": ["group-a", "group-b"],
    "rate_limiter_gatekeeper": {
        "requests_per_minute": 30, "concurrent_requests": 2,
        "retry_backoff_sec": 5, "max_retries": 3, "queue_depth": 100,
    },
}


def _write_config(config_root, role: str, mode: str = "draft"):
    config_root.mkdir(parents=True, exist_ok=True)
    (config_root / "game.json").write_text(json.dumps(SHARED_CONFIG))
    role_dir = config_root / role
    role_dir.mkdir(parents=True, exist_ok=True)
    (role_dir / "game.toml").write_text(
        f'[email]\nrecipient = "grader@example.com"\nmode = "{mode}"\n'
    )


def _derived_gid(config_root, role: str) -> str:
    # game_id is derived from the SHARED config.json alone, not the merged
    # per-role values -- both Police and Robber must compute the identical
    # id for the same match (Sec. 9.3), which only holds if private,
    # per-role-differing fields (network.my_port, etc.) are excluded.
    return derive_game_id(load_game_config(role, config_root).shared)


def test_run_report_draft_mode_never_calls_get_service(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path / "config", "police", mode="draft")
    gid = _derived_gid(tmp_path / "config", "police")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / f"result_{gid}.json").write_text(json.dumps({"winner": "me"}))

    with patch("police_thief.simulation_sdk.get_service") as mock_get_service:
        results = run_report("police", tmp_path / "config")

    mock_get_service.assert_not_called()
    assert len(results) == 1
    path, outcome = results[0]
    assert path.name == f"result_{gid}.json"
    assert outcome.name == f"draft_result_{gid}.eml"
    assert outcome.exists()


def test_run_report_send_mode_calls_get_service_and_gmail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path / "config", "police", mode="send")
    gid = _derived_gid(tmp_path / "config", "police")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / f"result_{gid}.json").write_text(json.dumps({"winner": "me"}))

    fake_service = MagicMock()
    fake_service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "msg1"
    }
    with patch("police_thief.simulation_sdk.get_service", return_value=fake_service) as mock_get_service:
        results = run_report("police", tmp_path / "config")

    mock_get_service.assert_called_once()
    assert results[0][1] == {"id": "msg1"}
    fake_service.users.return_value.messages.return_value.send.assert_called_once()


def test_run_report_raises_when_no_artifacts_exist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path / "config", "police")
    (tmp_path / "logs").mkdir()

    with pytest.raises(FileNotFoundError):
        run_report("police", tmp_path / "config")


def test_run_report_raises_when_recipient_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "game.json").write_text(json.dumps(SHARED_CONFIG))
    role_dir = config_root / "police"
    role_dir.mkdir()
    (role_dir / "game.toml").write_text("")  # no [email] section at all

    with pytest.raises(ValueError):
        run_report("police", config_root)
