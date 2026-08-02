"""Highest-cost provider: shells out to `claude -p` via the Claude Code CLI,
subject to the local subscription (Sec. 6.5.1)."""

from __future__ import annotations

import subprocess

from police_thief.infra.llm.base import SYSTEM_NOTE, LLMProvider, truncate_to_word_limit


class ClaudeCLIProvider(LLMProvider):
    def __init__(self, *, timeout_sec: float = 30):
        super().__init__()
        self.timeout_sec = timeout_sec

    def generate_hint(self, *, prompt: str, word_limit: int) -> str:
        full_prompt = f"{SYSTEM_NOTE.format(word_limit=word_limit)}\n\n{prompt}"
        try:
            result = subprocess.run(
                ["claude", "-p", full_prompt],
                capture_output=True, text=True, timeout=self.timeout_sec, check=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise RuntimeError(
                "claude CLI is unavailable -- is it installed and are you "
                "logged in (`claude auth login`)?"
            ) from exc
        # Plain-text stdout (`claude -p ...`) carries no usage/token metadata
        # -- unlike the other three providers, self.tokens_used has no way
        # to advance past 0 here without switching to a structured output
        # mode this provider doesn't use.
        return truncate_to_word_limit(result.stdout.strip(), word_limit)
