"""Google Gemini backend (HTTP)."""

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


def parse_gemini_sse_chunk(chunk: dict) -> tuple[str, str, dict]:
    """Map one Gemini SSE chunk to ``(text_delta, reasoning_delta, usage)``.

    Gemini marks thinking parts with ``thought: true``; everything else is
    answer text. Pure so the streaming loop stays testable.
    """
    text_out, reason_out = "", ""
    candidates = chunk.get("candidates") or []
    if candidates:
        parts = (candidates[0].get("content") or {}).get("parts") or []
        for part in parts:
            piece = part.get("text", "")
            if not piece:
                continue
            if part.get("thought"):
                reason_out += piece
            else:
                text_out += piece
    return text_out, reason_out, chunk.get("usageMetadata", {}) or {}


class GeminiBackend(LLMBackend):
    name = "gemini"
    env_key = "GEMINI_API_KEY"
    default_model = default_model("gemini", "gemini-3.1-pro")
    suggested_models = suggested_models("gemini")
    max_retries = 3

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

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={api_key}"
        )
        headers = {"Content-Type": "application/json"}
        # Gemini enables thinking automatically; we scale the output ceiling with
        # the user's reasoning tier rather than send a version-specific knob.
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": self.resolve_max_tokens(max_tokens),
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        if self.streaming:
            return self._generate_stream(api_key, headers, payload)

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

    def _generate_stream(
        self, api_key: str, headers: dict, payload: dict
    ) -> LLMResponse:
        """Streaming variant: parse Gemini SSE, emit deltas to ``on_stream``."""
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:streamGenerateContent?alt=sse&key={api_key}"
        )
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self._emit("", "start")
            text_parts: list[str] = []
            usage: dict = {}
            try:
                with requests.post(
                    url, headers=headers, json=payload, timeout=120, stream=True
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines(decode_unicode=True):
                        if not line or not line.startswith("data:"):
                            continue
                        try:
                            chunk = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        text_d, reason_d, usage_u = parse_gemini_sse_chunk(chunk)
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
                    "Gemini stream error (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

        logger.error("Gemini: max stream retries reached (%s)", last_error)
        return LLMResponse(text="", raw=last_error)
