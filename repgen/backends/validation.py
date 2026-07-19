"""Validate off-catalog model IDs against OpenRouter's public model list.

The static catalog in :mod:`repgen.backends.models` covers the models we
suggest, but users may type any model ID. When they enter something we don't
recognise, we cross-check it against OpenRouter's public ``/models`` endpoint
(no API key required) to decide whether to accept it or flag it as invalid.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import requests

logger = logging.getLogger("repgen.backends.validation")

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Map a RepGen backend name to the provider prefix OpenRouter uses in its model
# IDs (e.g. our bare ``gpt-5.5`` is ``openai/gpt-5.5`` on OpenRouter). Backends
# absent from this map are not validated against OpenRouter (e.g. local Ollama).
_OPENROUTER_PREFIX = {
    "openai": "openai",
    "claude": "anthropic",
    "gemini": "google",
    "openrouter": "",  # already namespaced
}

# Backends whose models cannot be meaningfully validated against OpenRouter.
_UNVALIDATABLE = {"ollama"}

_cache: Optional[frozenset] = None


def _fetch_openrouter_ids() -> frozenset:
    """Fetch and cache the set of model IDs OpenRouter serves."""
    global _cache
    if _cache is not None:
        return _cache
    response = requests.get(OPENROUTER_MODELS_URL, timeout=15)
    response.raise_for_status()
    data = response.json().get("data", [])
    _cache = frozenset(m["id"] for m in data if m.get("id"))
    return _cache


def _norm(model_id: str) -> str:
    """Canonicalise a model ID for comparison.

    Providers and OpenRouter disagree on version punctuation — native IDs use
    dashes (``gemini-3-pro``) while OpenRouter often uses dots
    (``google/gemini-3.1-flash-lite``). Fold dots to dashes and lowercase so the
    two forms match.
    """
    return model_id.lower().replace(".", "-")


def _candidates(backend: str, model: str) -> set:
    """Candidate OpenRouter IDs for a (backend, model) pair.

    Includes the raw ID and, for providers whose IDs we store un-namespaced,
    the ``<prefix>/<model>`` form OpenRouter expects.
    """
    prefix = _OPENROUTER_PREFIX.get(backend, "")
    candidates = {model}
    if prefix and "/" not in model:
        candidates.add(f"{prefix}/{model}")
    return candidates


def validate_model(backend: str, model: str) -> Tuple[Optional[bool], Optional[str]]:
    """Check whether ``model`` looks like a real model ID for ``backend``.

    Returns ``(is_valid, error)`` where ``is_valid`` is:
      * ``True``  — found on OpenRouter (accept it),
      * ``False`` — not found on OpenRouter (flag as an error),
      * ``None``  — could not be checked (backend not on OpenRouter, or the
        lookup failed); ``error`` explains why. Callers should not block the
        user on ``None`` — accept with a warning instead.
    """
    if backend in _UNVALIDATABLE:
        return None, f"{backend} models are local and can't be verified via OpenRouter"
    try:
        ids = _fetch_openrouter_ids()
    except Exception as e:  # noqa: BLE001 - network/parse errors are non-fatal
        logger.warning("OpenRouter model lookup failed: %s", e)
        return None, f"could not reach OpenRouter ({e})"
    known = {_norm(i) for i in ids}
    candidates = {_norm(c) for c in _candidates(backend, model)}
    return bool(candidates & known), None
