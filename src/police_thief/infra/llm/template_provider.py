"""Default provider: pre-written Python-side sentences, zero tokens, no
network dependency (Sec. 6.5.1). Recommended default -- keeps full budget
on the movement algorithm.

The literal hint text carries no honesty signal by itself -- whether a hint
is true or a calculated bluff is a separate, signed `Intent` field in the
Commit-Reveal protocol (Sec. 5.3), not something the text needs to encode.
"""

from __future__ import annotations

import random

from police_thief.infra.llm.base import LLMProvider

_GENERIC_LANDMARKS = [
    # Deliberately free of cardinal-direction words ("north"/"south"/etc.)
    # -- domain.belief.update_from_hint parses those as spatial cues, and a
    # landmark name accidentally containing one would silently perturb
    # belief with no strategic intent behind it (found via multi-seed
    # integration testing: "the north gate" was doing exactly this).
    "the old bridge", "the market square", "the harbor gate",
    "the clock tower", "the riverbank", "the alley behind the mill",
    "the boarded-up warehouse", "the train yard", "the fountain plaza",
]

_HINT_TEMPLATES = [
    "Slipping past {landmark}, still moving.",
    "Caught sight of {landmark} a moment ago.",
    "Doubling back near {landmark}.",
    "Holding position close to {landmark}.",
    "Lost track of {landmark}, pressing on regardless.",
    "Circling wide around {landmark}.",
    "Nothing but shadows near {landmark} tonight.",
    "Cutting through fast, {landmark} at my back.",
]


class TemplateProvider(LLMProvider):
    def __init__(self, *, landmarks: list[str] | None = None, rng: random.Random | None = None):
        super().__init__()
        self.landmarks = landmarks or list(_GENERIC_LANDMARKS)
        self._rng = rng or random.Random()

    def generate_hint(self, *, prompt: str, word_limit: int) -> str:
        template = self._rng.choice(_HINT_TEMPLATES)
        landmark = self._rng.choice(self.landmarks)
        text = template.format(landmark=landmark)
        words = text.split()
        if len(words) > word_limit:
            words = words[:word_limit]
        return " ".join(words)
