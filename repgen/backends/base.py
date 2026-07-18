"""Abstract LLM backend interface shared by all providers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("repgen.backends")


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

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or self.default_model
        self.api_key = api_key

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion for ``prompt`` and return an :class:`LLMResponse`."""

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
