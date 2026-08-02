"""Stage 4: the zero-token template LLM provider for the verbal bluff layer."""

import random

from police_thief.infra.llm.template_provider import TemplateProvider


def test_generate_hint_returns_nonempty_string():
    provider = TemplateProvider(rng=random.Random(0))
    hint = provider.generate_hint(prompt="", word_limit=15)
    assert isinstance(hint, str)
    assert len(hint) > 0


def test_generate_hint_respects_word_limit():
    provider = TemplateProvider(rng=random.Random(1))
    for _ in range(50):
        hint = provider.generate_hint(prompt="", word_limit=3)
        assert len(hint.split()) <= 3


def test_generate_hint_is_deterministic_given_seeded_rng():
    hint_a = TemplateProvider(rng=random.Random(42)).generate_hint(prompt="", word_limit=15)
    hint_b = TemplateProvider(rng=random.Random(42)).generate_hint(prompt="", word_limit=15)
    assert hint_a == hint_b


def test_generate_hint_uses_custom_landmarks_when_game_arena_is_set():
    provider = TemplateProvider(landmarks=["Times Square"], rng=random.Random(0))
    hint = provider.generate_hint(prompt="", word_limit=15)
    assert "Times Square" in hint


def test_generate_hint_costs_zero_tokens_no_network_dependency():
    # Nothing to mock -- the assertion IS that no network client is imported
    # or constructed anywhere in this module; if it were, this test file
    # would need a mock. Sanity check it can run fully offline repeatedly.
    provider = TemplateProvider(rng=random.Random(7))
    for _ in range(20):
        provider.generate_hint(prompt="anything", word_limit=15)
    assert provider.tokens_used == 0
