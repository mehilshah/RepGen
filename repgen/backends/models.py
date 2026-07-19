"""Provider-agnostic model catalog.

A single, easily-extended source of truth for which models each backend should
suggest interactively, and which one to default to. Backends read their
``default_model`` / ``suggested_models`` from here so that keeping up with new
state-of-the-art models is a one-line edit in this file rather than a change
spread across every backend class.

Each entry is a :class:`ModelSpec`. Adding a future model is just appending a
spec to the relevant provider list (and optionally flipping ``default=True``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ModelSpec:
    """A single selectable model."""

    id: str
    label: str = ""
    # Short capability tags for display (e.g. "reasoning", "coding", "fast").
    tags: tuple[str, ...] = ()
    default: bool = False

    def display(self) -> str:
        return self.label or self.id


@dataclass
class ProviderModels:
    """The catalog of models for one provider/backend."""

    models: List[ModelSpec] = field(default_factory=list)

    @property
    def default(self) -> Optional[str]:
        for m in self.models:
            if m.default:
                return m.id
        return self.models[0].id if self.models else None

    def ids(self) -> List[str]:
        return [m.id for m in self.models]


# --------------------------------------------------------------------------
# Catalog — newest / most capable first within each provider.
# --------------------------------------------------------------------------

MODEL_CATALOG: Dict[str, ProviderModels] = {
    "claude": ProviderModels(
        [
            ModelSpec("claude-opus-4-8", "Claude Opus 4.8",
                      ("reasoning", "coding", "agentic"), default=True),
            ModelSpec("claude-opus-4-7", "Claude Opus 4.7", ("reasoning", "coding")),
            ModelSpec("claude-opus-4-6", "Claude Opus 4.6", ("reasoning", "coding")),
            ModelSpec("claude-opus-4-5", "Claude Opus 4.5", ("reasoning", "coding")),
            ModelSpec("claude-fable-5", "Claude Fable 5",
                      ("frontier", "reasoning", "agentic")),
            ModelSpec("claude-sonnet-5", "Claude Sonnet 5", ("balanced", "coding")),
            ModelSpec("claude-sonnet-4-6", "Claude Sonnet 4.6", ("balanced", "coding")),
            ModelSpec("claude-sonnet-4-5", "Claude Sonnet 4.5", ("balanced", "coding")),
            ModelSpec("claude-haiku-4-5", "Claude Haiku 4.5", ("fast", "cheap")),
        ]
    ),
    "openai": ProviderModels(
        [
            ModelSpec("gpt-5.5", "GPT-5.5",
                      ("reasoning", "coding", "agentic"), default=True),
            ModelSpec("gpt-5.5-pro", "GPT-5.5 Pro", ("reasoning", "frontier")),
            ModelSpec("gpt-5.5-mini", "GPT-5.5 mini", ("fast", "cheap")),
            ModelSpec("gpt-5.4", "GPT-5.4", ("reasoning", "coding")),
            ModelSpec("gpt-5.3", "GPT-5.3", ("reasoning", "coding")),
            ModelSpec("gpt-5.2", "GPT-5.2", ("reasoning", "coding")),
            ModelSpec("gpt-5.1", "GPT-5.1", ("reasoning", "coding")),
            ModelSpec("gpt-5.1-mini", "GPT-5.1 mini", ("fast", "cheap")),
            ModelSpec("gpt-5", "GPT-5", ("reasoning", "coding")),
            ModelSpec("gpt-5-mini", "GPT-5 mini", ("fast", "cheap")),
            ModelSpec("gpt-5-nano", "GPT-5 nano", ("fast", "cheap")),
        ]
    ),
    "gemini": ProviderModels(
        [
            ModelSpec("gemini-3.1-pro", "Gemini 3.1 Pro",
                      ("reasoning", "coding"), default=True),
            ModelSpec("gemini-3.1-flash", "Gemini 3.1 Flash", ("fast", "agentic")),
            ModelSpec("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite",
                      ("fast", "cheap")),
            ModelSpec("gemini-3-pro", "Gemini 3 Pro", ("reasoning", "coding")),
            ModelSpec("gemini-3-flash", "Gemini 3 Flash", ("fast",)),
            ModelSpec("gemini-2.5-pro", "Gemini 2.5 Pro", ("reasoning",)),
            ModelSpec("gemini-2.5-flash", "Gemini 2.5 Flash", ("fast",)),
            ModelSpec("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite",
                      ("fast", "cheap")),
        ]
    ),
    "openrouter": ProviderModels(
        [
            ModelSpec("anthropic/claude-opus-4-8", "Claude Opus 4.8 (via OpenRouter)",
                      ("reasoning", "coding"), default=True),
            ModelSpec("openai/gpt-5.5", "GPT-5.5 (via OpenRouter)", ("reasoning",)),
            ModelSpec("google/gemini-3.1-pro", "Gemini 3.1 Pro (via OpenRouter)",
                      ("reasoning",)),
            ModelSpec("meta-llama/llama-3.1-70b-instruct", "Llama 3.1 70B",
                      ("open-weight",)),
        ]
    ),
    "ollama": ProviderModels(
        [
            ModelSpec("qwen2.5-coder", "Qwen2.5 Coder", ("coding", "local"),
                      default=True),
            ModelSpec("llama3.1", "Llama 3.1", ("local",)),
            ModelSpec("deepseek-coder-v2", "DeepSeek Coder V2", ("coding", "local")),
            ModelSpec("codellama", "Code Llama", ("coding", "local")),
        ]
    ),
}


def suggested_models(backend: str) -> tuple[str, ...]:
    """Return the suggested model IDs for a backend (empty if unknown)."""
    provider = MODEL_CATALOG.get(backend)
    return tuple(provider.ids()) if provider else ()


def default_model(backend: str, fallback: str = "") -> str:
    """Return the default model id for a backend, or ``fallback``."""
    provider = MODEL_CATALOG.get(backend)
    return (provider.default if provider else None) or fallback


def model_specs(backend: str) -> List[ModelSpec]:
    provider = MODEL_CATALOG.get(backend)
    return list(provider.models) if provider else []
