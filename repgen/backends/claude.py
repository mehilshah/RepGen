"""Anthropic Claude backend (HTTP)."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

import requests

from .base import LLMBackend, LLMResponse
from .models import default_model, suggested_models

logger = logging.getLogger("repgen.backends")


def parse_claude_sse_event(event: dict) -> tuple[str, str, dict]:
    """Map one Anthropic SSE event to ``(text_delta, reasoning_delta, usage)``.

    Pure and side-effect-free so the streaming loop stays trivial and testable.
    """
    etype = event.get("type")
    if etype == "content_block_delta":
        delta = event.get("delta", {})
        dtype = delta.get("type")
        if dtype == "text_delta":
            return delta.get("text", ""), "", {}
        if dtype == "thinking_delta":
            return "", delta.get("thinking", ""), {}
    elif etype == "message_start":
        return "", "", event.get("message", {}).get("usage", {}) or {}
    elif etype == "message_delta":
        return "", "", event.get("usage", {}) or {}
    return "", "", {}


class ClaudeBackend(LLMBackend):
    name = "claude"
    env_key = "ANTHROPIC_API_KEY"
    default_model = default_model("claude", "claude-opus-5-5")
    suggested_models = suggested_models("claude")
    max_retries = 3
    api_url = "https://api.anthropic.com/v1/messages"

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        api_key = self.api_key or os.getenv(self.env_key)
        if not api_key:
            logger.error("%s not set", self.env_key)
            return LLMResponse(text="")

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Modern payload: adaptive thinking + the user's effort tier. Current
        # models (Opus 4.8/4.7, Sonnet 5, Fable 5) reject `temperature` and
        # `budget_tokens` with a 400, and `max_tokens` is only a ceiling that
        # must hold thinking + the answer — which the effort tier sizes.
        payload = {
            "model": self.model,
            "max_tokens": self.resolve_max_tokens(max_tokens),
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort.value},
        }
        if system:
            payload["system"] = system

        if self.streaming:
            return self._generate_stream(headers, payload, temperature)

        # Whether we're still using the modern (effort/adaptive) shape. Older
        # models don't support it; on a 400 that names those fields we downgrade
        # once to a plain request (with temperature) and retry.
        modern = True
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url, headers=headers, json=payload, timeout=120
                )
                if response.status_code == 400 and modern:
                    body = response.text.lower()
                    if any(
                        k in body
                        for k in ("thinking", "effort", "output_config", "adaptive")
                    ):
                        payload.pop("thinking", None)
                        payload.pop("output_config", None)
                        payload["temperature"] = temperature
                        modern = False
                        logger.debug(
                            "Claude: model %s rejected adaptive/effort; "
                            "falling back to a plain request",
                            self.model,
                        )
                        continue
                response.raise_for_status()
                result = response.json()
                text = result["content"][0]["text"].strip()
                usage = result.get("usage", {})
                return LLMResponse(text=text, raw=result, usage=usage)
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.warning(
                    "Claude API error (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

        logger.error("Claude: max retries reached (%s)", last_error)
        return LLMResponse(text="", raw=last_error)

    def _generate_stream(
        self, headers: dict, payload: dict, temperature: float
    ) -> LLMResponse:
        """Streaming variant: parse Anthropic SSE, emit deltas to ``on_stream``.

        Thinking summaries stream as ``reasoning`` deltas (``display`` opt-in);
        the final answer streams as ``text``.
        """
        payload = {
            **payload,
            "stream": True,
            "thinking": {"type": "adaptive", "display": "summarized"},
        }
        modern = True
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self._emit("", "start")
            text_parts: list[str] = []
            usage: dict = {}
            try:
                with requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=120,
                    stream=True,
                ) as response:
                    if response.status_code == 400 and modern:
                        body = response.text.lower()
                        if any(
                            k in body
                            for k in ("thinking", "effort", "output_config", "adaptive")
                        ):
                            payload.pop("thinking", None)
                            payload.pop("output_config", None)
                            payload["temperature"] = temperature
                            modern = False
                            self._emit("", "end")
                            continue
                    response.raise_for_status()
                    for line in response.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        text_d, reason_d, usage_u = parse_claude_sse_event(event)
                        if text_d:
                            text_parts.append(text_d)
                            self._emit(text_d, "text")
                        if reason_d:
                            self._emit(reason_d, "reasoning")
                        if usage_u:
                            usage.update(usage_u)
                self._emit_usage(usage)
                self._emit("", "end")
                return LLMResponse(
                    text="".join(text_parts).strip(), raw=None, usage=usage
                )
            except Exception as e:  # noqa: BLE001
                self._emit("", "end")
                last_error = e
                logger.warning(
                    "Claude stream error (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

        logger.error("Claude: max stream retries reached (%s)", last_error)
        return LLMResponse(text="", raw=last_error)
