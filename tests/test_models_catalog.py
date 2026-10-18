"""Tests for the provider-agnostic model catalog."""

from __future__ import annotations

from repgen.backends import get_backend
from repgen.backends.models import (
    MODEL_CATALOG,
    default_model,
    model_specs,
    suggested_models,
)


def test_every_backend_has_a_default():
    for name, provider in MODEL_CATALOG.items():
        assert provider.default, f"{name} has no default model"


def test_claude_default_is_current_opus():
    assert default_model("claude") == "claude-opus-5-5"


def test_suggested_models_nonempty_for_known_backends():
    for name in ("claude", "openai", "gemini", "openrouter", "ollama"):
        assert suggested_models(name)


def test_unknown_backend_returns_empty():
    assert suggested_models("nope") == ()
    assert default_model("nope", "fallback") == "fallback"
    assert model_specs("nope") == []


def test_backend_reads_catalog():
    b = get_backend("claude")
    assert b.default_model == "claude-opus-5-5"
    assert "claude-sonnet-5" in b.list_models()


def test_exactly_one_default_per_provider():
    for provider in MODEL_CATALOG.values():
        defaults = [m for m in provider.models if m.default]
        assert len(defaults) == 1
