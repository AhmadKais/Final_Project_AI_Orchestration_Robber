"""Loads and merges the shared signed config (config/game.json) with the
private per-role config (config/<role>/game.toml).

Per Appendix B: shared JSON values always override matching TOML keys, so
the private file can never weaken a signed condition. Both peers must load
byte-for-byte identical JSON; config_sha256() is what gets cryptographically
locked before a series (Sec. 5.5, Appendix F rule 1).
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Role = Literal["police", "thief"]


@dataclass(frozen=True)
class GameConfig:
    """Merged, read-only view of shared + private config for one role."""

    role: Role
    values: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


def load_shared_config(path: Path) -> dict[str, Any]:
    """Load config/game.json. Raises if the file is missing or malformed."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_private_config(path: Path) -> dict[str, Any]:
    """Load config/<role>/game.toml."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def merge(shared: dict[str, Any], private: dict[str, Any]) -> dict[str, Any]:
    """Overlay: shared JSON keys win over private TOML keys (Appendix B --
    the private file can never weaken a signed condition)."""
    return {**private, **shared}


def config_sha256(shared: dict[str, Any]) -> str:
    """Canonical (sorted-keys, fixed-separator) SHA-256 of the shared config,
    used to prove both peers agreed on identical game physics (Sec. 5.5)."""
    canonical = json.dumps(shared, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def derive_game_id(shared: dict[str, Any]) -> str:
    """A `game_id` both peers can compute identically with zero extra
    negotiation round-trips (Sec. 9.3: the four per-series JSON artifacts
    -- declaration/config/log/results -- all share one `game_id`). Built
    from data both sides already hold identically before the first
    sub-game starts: the pre-agreed team pair (`agreed_between`, already
    in the signed shared config) and the shared config's own hash.

    `agreed_between` is sorted before hashing, not just for the display
    prefix: `config_sha256`'s `sort_keys=True` only normalizes DICT key
    order, not LIST element order, so two configs whose `agreed_between`
    lists happen to be written in a different order would otherwise hash
    to two different game IDs even though they represent the exact same
    agreed match between the exact same two teams."""
    normalized = {**shared, "agreed_between": sorted(shared.get("agreed_between", []))}
    groups = "-".join(normalized["agreed_between"])
    return f"{groups}_{config_sha256(normalized)[:8]}"


def load_game_config(role: Role, config_root: Path) -> GameConfig:
    """Convenience entry point: load + merge + return a GameConfig for `role`."""
    shared = load_shared_config(config_root / "game.json")
    private = load_private_config(config_root / role / "game.toml")
    return GameConfig(role=role, values=merge(shared, private))
