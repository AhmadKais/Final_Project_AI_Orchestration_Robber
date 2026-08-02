"""Common interface all four trash-talk providers implement."""

from __future__ import annotations

from abc import ABC, abstractmethod

SYSTEM_NOTE = (
    "Respond with only a short, in-character verbal hint for a pursuit "
    "game -- at most {word_limit} words, no explanation, just the line."
)


def truncate_to_word_limit(text: str, word_limit: int) -> str:
    """Enforce the hint word cap (default 15, Appendix F Table 14) even if
    the underlying model ignores the instruction in its system prompt."""
    words = text.split()
    if len(words) > word_limit:
        words = words[:word_limit]
    return " ".join(words)


class LLMProvider(ABC):
    def __init__(self) -> None:
        # Running total of real LLM tokens consumed by this provider
        # instance across every call so far (Rule 54: the end-of-game JSON
        # must report total tokens consumed, in the game and in the
        # series) -- a provider that has no real per-call token cost
        # (TemplateProvider, and ClaudeCLIProvider's plain-text stdout,
        # which exposes no usage figures) simply never advances this past 0.
        self.tokens_used: int = 0

    def _record_tokens(self, count: int) -> None:
        self.tokens_used += count

    @abstractmethod
    def generate_hint(self, *, prompt: str, word_limit: int) -> str:
        """Produce a verbal hint (true or a calculated bluff), capped at
        `word_limit` words (default 15, Appendix F Table 14)."""
        raise NotImplementedError
