"""LLM backend registry.

Provides a single entry point (:func:`get_backend`) for constructing any of the
supported providers, plus :func:`list_backends` for introspection (used by the
``repgen backends`` command).
"""

from __future__ import annotations

from typing import Optional

from .base import LLMBackend, LLMResponse
from .claude import ClaudeBackend
from .gemini import GeminiBackend
from .openai_backend import (
    OllamaBackend,
    OpenAIBackend,
    OpenRouterBackend,
)
from .reasoning import ReasoningEffort

# Ordered registry of provider name -> backend class.
BACKENDS: dict[str, type[LLMBackend]] = {
    OpenAIBackend.name: OpenAIBackend,
    ClaudeBackend.name: ClaudeBackend,
    GeminiBackend.name: GeminiBackend,
    OpenRouterBackend.name: OpenRouterBackend,
    OllamaBackend.name: OllamaBackend,
}

BACKEND_NAMES = list(BACKENDS.keys())


def get_backend(
    name: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    effort: "ReasoningEffort | str | None" = None,
) -> LLMBackend:
    """Instantiate a backend by name.

    Raises ``ValueError`` for an unknown backend name.
    """
    try:
        cls = BACKENDS[name]
    except KeyError:
        raise ValueError(
            f"Unknown backend '{name}'. Choose from: {', '.join(BACKEND_NAMES)}"
        ) from None
    return cls(model=model, api_key=api_key, effort=effort)


def list_backends() -> list[LLMBackend]:
    """Return one (unconfigured-model) instance per backend for introspection."""
    return [cls() for cls in BACKENDS.values()]


__all__ = [
    "LLMBackend",
    "LLMResponse",
    "ReasoningEffort",
    "BACKENDS",
    "BACKEND_NAMES",
    "get_backend",
    "list_backends",
    "OpenAIBackend",
    "OpenRouterBackend",
    "OllamaBackend",
    "ClaudeBackend",
    "GeminiBackend",
]
