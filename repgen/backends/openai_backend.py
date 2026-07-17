"""OpenAI and OpenAI-compatible backends (OpenRouter, Ollama)."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .base import LLMBackend, LLMResponse

logger = logging.getLogger("repgen.backends")


class OpenAICompatibleBackend(LLMBackend):
    """Base class for any provider exposing an OpenAI-compatible chat API.

    Subclasses override ``base_url`` (or leave ``None`` for the real OpenAI
    endpoint) and the identity attributes.
    """

    base_url: Optional[str] = None
    max_retries: int = 3

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "The 'openai' package is required. Install it with 'pip install openai'."
            ) from e

        api_key = self.api_key or (os.getenv(self.env_key) if self.env_key else None)
        # OpenAI-compatible servers (e.g. Ollama) still expect a non-empty key.
        return OpenAI(api_key=api_key or "not-needed", base_url=self.base_url)

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                client = self._client()
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content or ""
                usage = {}
                if getattr(response, "usage", None):
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                return LLMResponse(text=content.strip(), raw=response, usage=usage)
            except Exception as e:  # noqa: BLE001 - normalize all provider errors
                last_error = e
                logger.warning(
                    "%s API error (attempt %d/%d): %s",
                    self.name,
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

        logger.error("%s: max retries reached (%s)", self.name, last_error)
        return LLMResponse(text="", raw=last_error)


class OpenAIBackend(OpenAICompatibleBackend):
    name = "openai"
    env_key = "OPENAI_API_KEY"
    default_model = "gpt-4o"
    suggested_models = ("gpt-4o", "gpt-4o-mini", "gpt-4-turbo")
    base_url = None


class OpenRouterBackend(OpenAICompatibleBackend):
    name = "openrouter"
    env_key = "OPENROUTER_API_KEY"
    default_model = "openai/gpt-4o"
    suggested_models = (
        "openai/gpt-4o",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-pro-1.5",
        "meta-llama/llama-3.1-70b-instruct",
    )
    base_url = "https://openrouter.ai/api/v1"


class OllamaBackend(OpenAICompatibleBackend):
    name = "ollama"
    env_key = None  # local, keyless
    default_model = "llama3.1"
    suggested_models = ("llama3.1", "qwen2.5-coder", "codellama", "mistral")

    @property
    def base_url(self) -> str:  # type: ignore[override]
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        # Accept either a bare host or a full base_url in OLLAMA_HOST.
        if host.endswith("/v1"):
            return host
        return f"{host}/v1"
