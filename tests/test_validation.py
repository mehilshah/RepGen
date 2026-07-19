"""Tests for OpenRouter-backed model-ID validation (offline)."""

from __future__ import annotations

import pytest

from repgen.backends import validation


@pytest.fixture(autouse=True)
def _fake_openrouter(monkeypatch):
    """Serve a fixed OpenRouter model list; never touch the network."""
    monkeypatch.setattr(validation, "_cache", None)
    ids = frozenset(
        {
            "openai/gpt-5.5",
            "openai/gpt-5-mini",
            "anthropic/claude-opus-4.8",  # OpenRouter uses dot punctuation
            "google/gemini-3.1-flash-lite",
        }
    )
    monkeypatch.setattr(validation, "_fetch_openrouter_ids", lambda: ids)


def test_bare_openai_id_matches_namespaced():
    assert validation.validate_model("openai", "gpt-5.5") == (True, None)


def test_dot_dash_normalization_matches_claude():
    # We store dashes (claude-opus-4-8); OpenRouter serves dots — must still match.
    assert validation.validate_model("claude", "claude-opus-4-8") == (True, None)


def test_gemini_flash_lite_matches():
    assert validation.validate_model("gemini", "gemini-3.1-flash-lite") == (True, None)


def test_unknown_model_is_flagged():
    is_valid, err = validation.validate_model("openai", "gpt-does-not-exist")
    assert is_valid is False and err is None


def test_ollama_is_unverifiable():
    is_valid, err = validation.validate_model("ollama", "llama3.1")
    assert is_valid is None and "local" in err


def test_lookup_failure_is_non_fatal(monkeypatch):
    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(validation, "_fetch_openrouter_ids", boom)
    is_valid, err = validation.validate_model("openai", "gpt-5.5")
    assert is_valid is None and "OpenRouter" in err
