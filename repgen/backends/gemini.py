"""Google Gemini backend (HTTP)."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests

from .base import LLMBackend, LLMResponse

logger = logging.getLogger("repgen.backends")


class GeminiBackend(LLMBackend):
    name = "gemini"
    env_key = "GEMINI_API_KEY"
    default_model = "gemini-1.5-pro"
    suggested_models = ("gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash")
    max_retries = 3

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

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={api_key}"
        )
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url, headers=headers, json=payload, timeout=120
                )
                response.raise_for_status()
                result = response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                usage = result.get("usageMetadata", {})
                return LLMResponse(text=text, raw=result, usage=usage)
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.warning(
                    "Gemini API error (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

        logger.error("Gemini: max retries reached (%s)", last_error)
        return LLMResponse(text="", raw=last_error)
