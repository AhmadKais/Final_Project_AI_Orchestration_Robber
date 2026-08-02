"""Local model via Ollama (e.g. localhost:11434) -- zero API tokens, no rate limit."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from police_thief.infra.llm.base import SYSTEM_NOTE, LLMProvider, truncate_to_word_limit


class OllamaProvider(LLMProvider):
    def __init__(self, *, base_url: str = "http://localhost:11434", model: str = "llama3", timeout_sec: float = 30):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_sec = timeout_sec

    def generate_hint(self, *, prompt: str, word_limit: int) -> str:
        full_prompt = f"{SYSTEM_NOTE.format(word_limit=word_limit)}\n\n{prompt}"
        payload = json.dumps({"model": self.model, "prompt": full_prompt, "stream": False}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/generate", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(
                f"Ollama at {self.base_url} is unreachable -- is it running "
                f"(`ollama serve`) with model {self.model!r} pulled?"
            ) from exc
        # Ollama's non-streaming response reports real local-model token
        # counts (prompt_eval_count/eval_count) -- zero API cost (Appendix F
        # Table 21), but still real tokens consumed by the model itself, so
        # Rule 54's total should include them.
        self._record_tokens(body.get("prompt_eval_count", 0) + body.get("eval_count", 0))
        return truncate_to_word_limit(body.get("response", "").strip(), word_limit)
