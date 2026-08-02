"""Step-0 hardware/software declaration for computational fairness (Sec. 5.5).

Collects OS, CPU core count/frequency, RAM, GPU/VRAM presence, the LLM in
use, code version, and the GitHub commit hash actually played, plus this
team's repo links, roster, and running league game count (Rules 37 & 49) --
packed into a JSON string and signed before the first move.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Step0Declaration:
    os_name: str
    cpu_cores: int
    cpu_freq_mhz: float
    ram_gb: float
    gpu: str | None
    vram_gb: float | None
    llm_model: str
    code_version: str
    github_commit: str
    group_name: str
    sub_game_number: int
    # Exchanged here (not just held locally) so the opponent's real values
    # land in the [Declaration File] via the same Step-0 round-trip that
    # already carries group_name and hardware -- Rule 49 ("four links in
    # the JSON of both teams") and Rule 37 ("declare precisely the number
    # of games actually played at the start of every game").
    repo_cop: str = ""
    repo_thief: str = ""
    members: tuple[str, ...] = ()
    games_played_so_far: int = 0
    # Hash of the SHARED config.json only (Rule 11: "ensure the
    # configuration file is completely identical, byte-for-byte, on both
    # sides") -- exchanged here so each side can refuse to play on a
    # mismatch, same round-trip as everything else above.
    config_sha256: str = ""


def _cpu_freq_mhz() -> float:
    """Best-effort CPU frequency from /proc/cpuinfo (Linux). Not fatal if
    unavailable -- computational fairness only needs a good-faith reading,
    not a guaranteed one on every platform."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("cpu mhz"):
                    return float(line.split(":")[1].strip())
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def _ram_gb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 2)
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def _gpu_info() -> tuple[str | None, float | None]:
    if not shutil.which("nvidia-smi"):
        return None, None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        name, vram_mib = out.split(",")
        return name.strip(), round(float(vram_mib.strip()) / 1024, 2)
    except (subprocess.SubprocessError, ValueError, OSError):
        return "GPU detected (nvidia-smi query failed)", None


def collect_step0_declaration(*, code_version: str, github_commit: str,
                               group_name: str, sub_game_number: int,
                               llm_model: str, repo_cop: str = "", repo_thief: str = "",
                               members: tuple[str, ...] | list[str] = (),
                               games_played_so_far: int = 0,
                               config_sha256: str = "") -> Step0Declaration:
    """Gather live hardware/software facts for this machine."""
    gpu, vram_gb = _gpu_info()
    return Step0Declaration(
        os_name=f"{platform.system()} {platform.release()}",
        cpu_cores=os.cpu_count() or 0,
        cpu_freq_mhz=_cpu_freq_mhz(),
        ram_gb=_ram_gb(),
        gpu=gpu,
        vram_gb=vram_gb,
        llm_model=llm_model,
        code_version=code_version,
        github_commit=github_commit,
        group_name=group_name,
        sub_game_number=sub_game_number,
        repo_cop=repo_cop,
        repo_thief=repo_thief,
        members=tuple(members),
        games_played_so_far=games_played_so_far,
        config_sha256=config_sha256,
    )


def sign_declaration(declaration: Step0Declaration, signing_key: bytes) -> str:
    """HMAC-SHA256 over the canonical declaration, so it cannot be forged
    or altered after the fact without invalidating the signature."""
    canonical = json.dumps(asdict(declaration), sort_keys=True, separators=(",", ":"))
    return hmac.new(signing_key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
