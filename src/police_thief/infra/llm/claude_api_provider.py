"""Cloud model via the Anthropic API (e.g. Haiku) -- real token consumption,
counted against token_budget_per_series (Appendix F Table 18)."""

from __future__ import annotations

from police_thief.infra.llm.base import SYSTEM_NOTE, LLMProvider, truncate_to_word_limit


class ClaudeAPIProvider(LLMProvider):
    def __init__(self, *, model: str = "claude-haiku-4-5", api_key: str | None = None):
        super().__init__()
        self.model = model
        self.api_key = api_key

    def generate_hint(self, *, prompt: str, word_limit: int) -> str:
        import anthropic  # deferred: only needed when this provider is actually selected

        client = anthropic.Anthropic(api_key=self.api_key)  # falls back to ANTHROPIC_API_KEY env var
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=64,
                system=SYSTEM_NOTE.format(word_limit=word_limit),
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AnthropicError as exc:
            raise RuntimeError(f"Claude API call failed for model {self.model!r}: {exc}") from exc

        # Real, billed token consumption (Rule 54: must be reported in the
        # end-of-game JSON, in the game and in the series) -- the only one
        # of the four providers where this actually costs money.
        self._record_tokens(response.usage.input_tokens + response.usage.output_tokens)
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return truncate_to_word_limit(text, word_limit)
