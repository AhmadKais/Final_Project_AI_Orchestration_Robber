"""Shared signed config (game.json) merged with private per-role config
(game.toml) -- Appendix B: shared JSON always wins on key collisions."""

import json

import pytest

from police_thief.shared.config_manager import (
    config_sha256,
    derive_game_id,
    load_game_config,
    load_private_config,
    load_shared_config,
    merge,
)


def test_load_shared_config_reads_json(tmp_path):
    path = tmp_path / "game.json"
    path.write_text(json.dumps({"board_and_agents": {"grid_size": 7}}))

    loaded = load_shared_config(path)

    assert loaded == {"board_and_agents": {"grid_size": 7}}


def test_load_shared_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_shared_config(tmp_path / "does_not_exist.json")


def test_load_private_config_reads_toml(tmp_path):
    path = tmp_path / "game.toml"
    path.write_text('[network]\nmy_port = 8801\nopponent_url = "http://x/mcp"\n')

    loaded = load_private_config(path)

    assert loaded == {"network": {"my_port": 8801, "opponent_url": "http://x/mcp"}}


def test_merge_shared_keys_win_on_collision():
    shared = {"network": {"from": "shared"}}
    private = {"network": {"from": "private"}, "strategy": {"police_class": "x"}}

    merged = merge(shared, private)

    assert merged["network"] == {"from": "shared"}  # shared wins the top-level key
    assert merged["strategy"] == {"police_class": "x"}  # untouched private-only key


def test_config_sha256_is_deterministic_regardless_of_key_order():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert config_sha256(a) == config_sha256(b)


def test_config_sha256_changes_with_content():
    assert config_sha256({"a": 1}) != config_sha256({"a": 2})


def test_load_game_config_merges_shared_and_private(tmp_path):
    config_root = tmp_path / "config"
    (config_root / "police").mkdir(parents=True)
    (config_root / "game.json").write_text(json.dumps({"board_and_agents": {"grid_size": 7}}))
    (config_root / "police" / "game.toml").write_text('[network]\nmy_port = 8801\n')

    game_config = load_game_config("police", config_root)

    assert game_config.role == "police"
    assert game_config["board_and_agents"]["grid_size"] == 7
    assert game_config["network"]["my_port"] == 8801


def test_load_game_config_shared_overrides_conflicting_private_key(tmp_path):
    config_root = tmp_path / "config"
    (config_root / "thief").mkdir(parents=True)
    (config_root / "game.json").write_text(json.dumps({"movement_and_barriers": {"max_moves": 35}}))
    (config_root / "thief" / "game.toml").write_text(
        "[movement_and_barriers]\nmax_moves = 5\n"  # private attempt to weaken a signed condition
    )

    game_config = load_game_config("thief", config_root)

    assert game_config["movement_and_barriers"]["max_moves"] == 35  # signed value wins


# -- derive_game_id: both peers compute the identical id, zero extra round-trips --

def test_derive_game_id_is_order_independent_in_agreed_between():
    a = {"agreed_between": ["group-a", "group-b"], "x": 1}
    b = {"agreed_between": ["group-b", "group-a"], "x": 1}
    assert derive_game_id(a) == derive_game_id(b)  # sorted -- doesn't matter who's "first"


def test_derive_game_id_changes_with_config_content():
    a = {"agreed_between": ["group-a", "group-b"], "x": 1}
    b = {"agreed_between": ["group-a", "group-b"], "x": 2}
    assert derive_game_id(a) != derive_game_id(b)


def test_derive_game_id_changes_with_different_team_pair():
    a = {"agreed_between": ["group-a", "group-b"], "x": 1}
    b = {"agreed_between": ["group-a", "group-c"], "x": 1}
    assert derive_game_id(a) != derive_game_id(b)
