"""Anthropic Claude backend (HTTP)."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests

from .base import LLMBackend, LLMResponse

logger = logging.getLogger("repgen.backends")


class ClaudeBackend(LLMBackend):
    name = "claude"
    env_key = "ANTHROPIC_API_KEY"
    default_model = "claude-sonnet-4-5"
    suggested_models = (
        "claude-sonnet-4-5",
        "claude-opus-4-1",
        "claude-3-5-sonnet-20241022",
    )
    max_retries = 3
    api_url = "https://api.anthropic.com/v1/messages"

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
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
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url, headers=headers, json=payload, timeout=120
                )
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
