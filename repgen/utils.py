"""Shared helpers: LLM dispatch shim and text extraction utilities.

Input handling lives in :mod:`repgen.inputs`, prompts in :mod:`repgen.prompts`,
and the Rich console in :mod:`repgen.console`. This module keeps a small,
backend-agnostic surface used throughout the agent.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .backends import get_backend
from .console import console  # re-exported for backwards compatibility

logger = logging.getLogger("repgen.utils")

__all__ = ["console", "query_llm", "extract_json_content"]


def query_llm(
    prompt: str,
    backend: str,
    model: str,
    api_key: Optional[str] = None,
    *,
    system: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """Convenience shim: dispatch a single prompt to a backend, return its text.

    Prefer constructing a backend via :func:`repgen.backends.get_backend` when
    issuing many calls; this keeps call sites that only need a one-shot string.
    """
    try:
        client = get_backend(backend, model, api_key)
    except ValueError as e:
        logger.error("%s", e)
        return ""
    return client.generate(
        prompt, system=system, temperature=temperature, max_tokens=max_tokens
    ).text


def extract_json_content(text: str) -> Optional[str]:
    """Extract a JSON/code payload from a possibly fenced LLM response."""
    if not text:
        return None
    pattern = r"```(?:[a-zA-Z0-9_\-+]+)?\s*(.*?)\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    stripped = text.strip()
    if (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    ):
        return stripped
    return None
