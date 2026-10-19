"""Abstract LLM backend interface shared by all providers."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .reasoning import ReasoningEffort

logger = logging.getLogger("repgen.backends")

# Callback for live output: (delta, kind) where kind is one of
# "start" | "text" | "reasoning" | "usage" | "end". "start"/"end" bracket a
# single call (delta is empty); "text"/"reasoning" carry incremental output;
# "usage" carries a JSON-encoded token-usage dict emitted just before "end".
StreamCallback = Optional[Callable[[str, str], None]]


def normalize_usage(usage: dict) -> dict:
    """Map any provider's token-usage dict to canonical keys.

    Providers name their token counts differently — OpenAI uses
    ``completion_tokens``/``reasoning_tokens``, Anthropic ``output_tokens`` (with
    thinking folded in), Gemini ``candidatesTokenCount``/``thoughtsTokenCount``.
    This flattens them to ``input_tokens``/``output_tokens``/``reasoning_tokens``/
    ``total_tokens`` so the UI can show real numbers regardless of backend.
    """
    if not usage:
        return {}

    def pick(*keys):
        for key in keys:
            value = usage.get(key)
            if value is not None:
                return value
        return None

    output_tokens = pick("completion_tokens", "output_tokens", "candidatesTokenCount")
    reasoning_tokens = pick("reasoning_tokens", "thoughtsTokenCount")

    # OpenAI's ``completion_tokens`` includes hidden reasoning tokens.  Other
    # providers' canonical ``output_tokens`` / ``candidatesTokenCount`` do not,
    # so only adjust the OpenAI-shaped payload.  Without this, the renderer
    # reports hidden reasoning twice: once as output and once as thinking.
    if (
        "completion_tokens" in usage
        and output_tokens is not None
        and reasoning_tokens is not None
    ):
        output_tokens = max(0, output_tokens - reasoning_tokens)

    canonical = {
        "input_tokens": pick("prompt_tokens", "input_tokens", "promptTokenCount"),
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": pick("total_tokens", "totalTokenCount"),
    }
    return {k: v for k, v in canonical.items() if v is not None}


@dataclass
class LLMResponse:
    """Normalized response from any backend."""

    text: str
    raw: Any = None
    usage: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.text)


class LLMBackend(ABC):
    """Common interface implemented by every provider backend.

    Subclasses set the class attributes ``name``, ``env_key`` (the environment
    variable holding the API key, or ``None`` for keyless local backends) and
    ``default_model``; and implement :meth:`generate`.
    """

    name: str = "base"
    env_key: Optional[str] = None
    default_model: str = ""
    suggested_models: tuple[str, ...] = ()

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        effort: "ReasoningEffort | str | None" = None,
    ):
        self.model = model or self.default_model
        self.api_key = api_key
        # The user's chosen reasoning tier drives the native reasoning level and
        # the default token ceiling for every call (see :mod:`.reasoning`).
        self.effort = ReasoningEffort.coerce(effort)
        # When set (by the CLI), backends stream output live to this callback.
        # Left None everywhere else so the non-streaming path is unchanged.
        self.on_stream: StreamCallback = None

    def _emit(self, delta: str, kind: str = "text") -> None:
        """Push a streaming delta to the renderer, if one is attached."""
        cb = self.on_stream
        if cb is None:
            return
        try:
            cb(delta, kind)
        except Exception:  # noqa: BLE001 - rendering must never break a run
            pass

    def _emit_usage(self, usage: dict) -> None:
        """Emit the call's token usage to the renderer just before ``end``.

        Sent as a JSON string under the ``usage`` kind so the live renderer can
        show the *real* output/reasoning token counts (reasoning models rarely
        stream their thinking, so a char-based estimate reads as ~0).
        """
        if not usage or self.on_stream is None:
            return
        try:
            self._emit(json.dumps(normalize_usage(usage)), "usage")
        except Exception:  # noqa: BLE001 - usage reporting is best-effort
            pass

    @property
    def streaming(self) -> bool:
        return self.on_stream is not None

    def resolve_max_tokens(self, requested: Optional[int]) -> int:
        """Resolve the effective ``max_tokens`` for a call.

        ``None`` means "use whatever the user's reasoning tier allows" — this is
        the default so token limits are the user's decision (via the effort
        control), not a magic constant buried in a call site.
        """
        return requested if requested is not None else self.effort.max_tokens

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate a completion for ``prompt`` and return an :class:`LLMResponse`.

        ``max_tokens=None`` inherits the ceiling from the user's reasoning tier.
        """

    def is_configured(self) -> bool:
        """Whether the backend has everything it needs to run (key/endpoint)."""
        import os

        if self.env_key is None:
            return True  # keyless (e.g. local Ollama)
        return bool(self.api_key or os.getenv(self.env_key))

    def list_models(self) -> list[str]:
        """Best-effort list of model names to suggest interactively."""
        return list(self.suggested_models)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<{type(self).__name__} model={self.model!r}>"
