"""User-facing reasoning-effort control shared by all backends.

Rather than asking users for a raw token count — meaningless to most people and
easy to set wrong — RepGen exposes a single named tier, the pattern the major
APIs converged on (OpenAI's ``reasoning_effort``, Anthropic's adaptive-thinking
``effort``). The user picks *how hard to think*; RepGen sizes the answer ceiling
internally.

Each tier maps to two things:

* A provider-native reasoning level (``low`` / ``medium`` / ``high``) — passed as
  ``reasoning_effort`` to OpenAI-compatible backends and as
  ``output_config.effort`` (with adaptive thinking) to Claude.
* A ``max_tokens`` ceiling for *every* operation. On adaptive-thinking models
  ``max_tokens`` must hold thinking + the final answer + headroom, so a higher
  effort needs a higher ceiling or the answer is starved before it is emitted
  (exactly the failure that silently forced the planner's heuristic fallback).

The ceilings assume a final answer in the low-thousands of tokens and leave the
rest for reasoning, keeping thinking at roughly half the budget at higher tiers.
"""

from __future__ import annotations

from enum import Enum


class ReasoningEffort(str, Enum):
    """How hard the model should think, as a named tier."""

    LOW = "low"  # Quick — latency/cost-sensitive (classification, short gen)
    MEDIUM = "medium"  # Balanced — the default
    HIGH = "high"  # Thorough — multi-step reasoning, hard analysis

    @classmethod
    def coerce(cls, value: "ReasoningEffort | str | None") -> "ReasoningEffort":
        """Best-effort parse of a user/config value; defaults to MEDIUM."""
        if isinstance(value, cls):
            return value
        if not value:
            return cls.MEDIUM
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.MEDIUM

    @property
    def max_tokens(self) -> int:
        """The ``max_tokens`` ceiling all operations inherit at this tier."""
        return {
            ReasoningEffort.LOW: 8000,
            ReasoningEffort.MEDIUM: 16000,
            ReasoningEffort.HIGH: 64000,
        }[self]

    @property
    def label(self) -> str:
        """Human-facing name for the tier."""
        return {
            ReasoningEffort.LOW: "Quick",
            ReasoningEffort.MEDIUM: "Balanced",
            ReasoningEffort.HIGH: "Thorough",
        }[self]

    @property
    def description(self) -> str:
        return {
            ReasoningEffort.LOW: "fast, latency-sensitive; least thinking",
            ReasoningEffort.MEDIUM: "the default balance of quality and cost",
            ReasoningEffort.HIGH: "hardest reasoning; most thinking (slower, pricier)",
        }[self]
