"""_load_signing_key: real per-team HMAC key from a local, gitignored .env
(Sec. 5.5: "signed using a key supplied in advance"), falling back to the
shipped placeholder when .env doesn't set one."""

from police_thief.simulation_sdk import _load_signing_key


def test_falls_back_to_placeholder_when_no_env_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _load_signing_key() == b"local-dev-key-replace-in-production"


def test_falls_back_to_placeholder_when_env_file_has_no_signing_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GITHUB_TOKEN=ghp_something\n")
    assert _load_signing_key() == b"local-dev-key-replace-in-production"


def test_reads_real_signing_key_from_env_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GITHUB_TOKEN=ghp_something\nSIGNING_KEY=abc123def456\n")
    assert _load_signing_key() == b"abc123def456"
