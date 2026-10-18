"""OpenAI and OpenAI-compatible backends (OpenRouter, Ollama)."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional

from .base import LLMBackend, LLMResponse
from .models import default_model, suggested_models

logger = logging.getLogger("repgen.backends")


def _uses_openai_reasoning_params(model: str) -> bool:
    """Whether an official OpenAI model uses the reasoning chat parameters.

    GPT-5/6 and o-series models reject ``max_tokens`` and non-default
    temperatures.  Avoiding those known-invalid fields prevents two noisy 400
    responses before every successful request.  Compatible third-party
    backends still retain the adaptive fallback below.
    """
    model_id = model.rsplit("/", 1)[-1].lower()
    return bool(re.match(r"^(?:gpt-[56](?:[.-]|$)|o[1-9](?:[.-]|$))", model_id))


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

    @staticmethod
    def _adapt_params(params: dict, error: Exception) -> bool:
        """React to a provider "unsupported parameter/value" error by adjusting
        the request in place. Returns ``True`` if something changed so the caller
        should retry immediately.

        Model generations differ: newer OpenAI models rename ``max_tokens`` to
        ``max_completion_tokens`` and only accept the default temperature, while
        OpenAI-compatible servers vary. Rather than hardcode per-model rules, we
        adapt when the server tells us a parameter is unsupported. Each branch
        removes or renames the offending key, so adaptation always converges.
        """
        msg = str(error).lower()
        if "unsupported" not in msg and "not supported" not in msg:
            return False
        if "max_tokens" in params and "max_completion_tokens" in msg:
            params["max_completion_tokens"] = params.pop("max_tokens")
            return True
        if "temperature" in params and "temperature" in msg:
            params.pop("temperature")
            return True
        # Non-reasoning models (and some OpenAI-compatible servers, e.g. Ollama)
        # reject reasoning_effort — drop it and continue rather than fail.
        if "reasoning_effort" in params and "reasoning_effort" in msg:
            params.pop("reasoning_effort")
            return True
        # Some OpenAI-compatible servers reject stream usage accounting.
        if "stream_options" in params and "stream_options" in msg:
            params.pop("stream_options")
            return True
        return False

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        params: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.resolve_max_tokens(max_tokens),
            # Native reasoning control for reasoning models (gpt-5.x, etc.).
            # Stripped by _adapt_params on servers/models that don't accept it.
            "reasoning_effort": self.effort.value,
        }

        # These rules are specific to OpenAI's API.  OpenRouter and local
        # OpenAI-compatible servers can expose similarly named models with
        # different parameter support, so let their existing error adaptation
        # handle any mismatch.
        if self.name == "openai" and _uses_openai_reasoning_params(self.model):
            params["max_completion_tokens"] = params.pop("max_tokens")
            params.pop("temperature")

        if self.streaming:
            return self._generate_stream(params)

        last_error: Optional[Exception] = None
        attempt = 0
        while attempt < self.max_retries:
            try:
                client = self._client()
                response = client.chat.completions.create(**params)
                content = response.choices[0].message.content or ""
                usage = {}
                if getattr(response, "usage", None):
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                    # Reasoning models report how much of the completion was
                    # spent thinking — surface it so a near-empty answer with a
                    # huge reasoning count is visible rather than mysterious.
                    details = getattr(
                        response.usage, "completion_tokens_details", None
                    )
                    reasoning = getattr(details, "reasoning_tokens", None)
                    if reasoning is not None:
                        usage["reasoning_tokens"] = reasoning
                return LLMResponse(text=content.strip(), raw=response, usage=usage)
            except Exception as e:  # noqa: BLE001 - normalize all provider errors
                # A model may reject a specific parameter (e.g. GPT-5 wants
                # 'max_completion_tokens' and only the default temperature).
                # Adapt and retry without spending a network retry.
                if self._adapt_params(params, e):
                    logger.debug(
                        "%s: adapting request after unsupported-parameter error",
                        self.name,
                    )
                    continue
                last_error = e
                attempt += 1
                logger.warning(
                    "%s API error (attempt %d/%d): %s",
                    self.name,
                    attempt,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))

        logger.error("%s: max retries reached (%s)", self.name, last_error)
        return LLMResponse(text="", raw=last_error)

    def _generate_stream(self, params: dict) -> LLMResponse:
        """Streaming variant: emit text/reasoning deltas live to ``on_stream``.

        Reasoning models don't stream their raw thinking as content, so we emit
        any ``reasoning``/``reasoning_content`` deltas that OpenAI-compatible
        proxies (e.g. OpenRouter) do expose, and always report the final
        ``reasoning_tokens`` from the usage chunk.
        """
        params = {**params, "stream": True, "stream_options": {"include_usage": True}}
        last_error: Optional[Exception] = None
        attempt = 0
        self._emit("", "start")
        while attempt < self.max_retries:
            text_parts: list[str] = []
            usage: dict = {}
            try:
                client = self._client()
                for chunk in client.chat.completions.create(**params):
                    if getattr(chunk, "usage", None):
                        usage = _stream_usage(chunk.usage)
                    if not getattr(chunk, "choices", None):
                        continue
                    delta = chunk.choices[0].delta
                    piece = getattr(delta, "content", None)
                    if piece:
                        text_parts.append(piece)
                        self._emit(piece, "text")
                    reasoning = getattr(delta, "reasoning_content", None) or getattr(
                        delta, "reasoning", None
                    )
                    if reasoning:
                        self._emit(reasoning, "reasoning")
                self._emit_usage(usage)
                self._emit("", "end")
                return LLMResponse(
                    text="".join(text_parts).strip(), raw=None, usage=usage
                )
            except Exception as e:  # noqa: BLE001 - normalize all provider errors
                if self._adapt_params(params, e):
                    logger.debug(
                        "%s: adapting stream request after unsupported param",
                        self.name,
                    )
                    continue
                last_error = e
                attempt += 1
                logger.warning(
                    "%s stream error (attempt %d/%d): %s",
                    self.name,
                    attempt,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))

        logger.error("%s: max stream retries reached (%s)", self.name, last_error)
        self._emit("", "end")
        return LLMResponse(text="", raw=last_error)


def _stream_usage(usage_obj) -> dict:
    """Normalize a streamed usage object into RepGen's usage dict."""
    usage = {
        "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
        "completion_tokens": getattr(usage_obj, "completion_tokens", None),
        "total_tokens": getattr(usage_obj, "total_tokens", None),
    }
    details = getattr(usage_obj, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None)
    if reasoning is not None:
        usage["reasoning_tokens"] = reasoning
    return {k: v for k, v in usage.items() if v is not None}


class OpenAIBackend(OpenAICompatibleBackend):
    name = "openai"
    env_key = "OPENAI_API_KEY"
    default_model = default_model("openai", "gpt-6-astra")
    suggested_models = suggested_models("openai")
    base_url = None


class OpenRouterBackend(OpenAICompatibleBackend):
    name = "openrouter"
    env_key = "OPENROUTER_API_KEY"
    default_model = default_model("openrouter", "openai/gpt-6-astra")
    suggested_models = suggested_models("openrouter")
    base_url = "https://openrouter.ai/api/v1"


class OllamaBackend(OpenAICompatibleBackend):
    name = "ollama"
    env_key = None  # local, keyless
    default_model = default_model("ollama", "qwen3-coder")
    suggested_models = suggested_models("ollama")

    @property
    def base_url(self) -> str:  # type: ignore[override]
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        # Accept either a bare host or a full base_url in OLLAMA_HOST.
        if host.endswith("/v1"):
            return host
        return f"{host}/v1"
