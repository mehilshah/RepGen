"""Verifier pipeline: runs the static stages in order and aggregates results."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from ..backends import LLMBackend
from ..prompts import failure_signature_prompt
from ..utils import extract_json_content
from .verifiers import (
    CompilationVerifier,
    CritiqueVerifier,
    FailureSignature,
    Feedback,
    SymbolicVerifier,
    SyntaxVerifier,
    VerificationContext,
    Verifier,
)

logger = logging.getLogger("repgen.agent.feedback")


@dataclass
class VerificationResult:
    passed: bool
    feedbacks: List[Feedback] = field(default_factory=list)
    # True when the symbolic stage found an unresolved repo symbol, signalling
    # that re-exploration may help.
    needs_reexploration: bool = False

    def repair_text(self) -> str:
        """Concatenated, actionable feedback for the next generation attempt."""
        blocks = [fb.render() for fb in self.feedbacks if not fb.passed]
        return "\n".join(blocks)


def extract_failure_signature(
    refined_report: str, backend: Optional[LLMBackend]
) -> FailureSignature:
    """Ask the LLM for the expected failure signature (best effort)."""
    if backend is None:
        return FailureSignature()
    raw = backend.generate(
        failure_signature_prompt(refined_report)
    ).text
    payload = extract_json_content(raw) or raw
    try:
        data = json.loads(payload)
    except Exception:  # noqa: BLE001
        return FailureSignature()
    return FailureSignature(
        exception_type=data.get("exception_type"),
        message_substrings=[s for s in (data.get("message_substrings") or []) if s],
        trigger_apis=[s for s in (data.get("trigger_apis") or []) if s],
    )


class FeedbackPipeline:
    """Runs verifiers in order; stops early on a blocking static failure."""

    def __init__(self, verifiers: Optional[List[Verifier]] = None):
        self.verifiers = verifiers or [
            SyntaxVerifier(),
            CompilationVerifier(),
            SymbolicVerifier(),
            CritiqueVerifier(),
        ]

    def run(self, code: str, ctx: VerificationContext) -> VerificationResult:
        feedbacks: List[Feedback] = []
        needs_reexplore = False
        for verifier in self.verifiers:
            fb = verifier.verify(code, ctx)
            feedbacks.append(fb)
            if verifier.stage == "symbolic":
                needs_reexplore = any(
                    "not defined in module" in f.message or "never defined" in f.message
                    for f in fb.findings
                )
            # Stop the static chain early on a blocking failure so we don't ask
            # the LLM judge to critique code that won't even compile.
            if fb.blocking and verifier.stage in ("syntax", "compilation"):
                return VerificationResult(
                    passed=False,
                    feedbacks=feedbacks,
                    needs_reexploration=needs_reexplore,
                )
        passed = all(fb.passed for fb in feedbacks)
        return VerificationResult(
            passed=passed, feedbacks=feedbacks, needs_reexploration=needs_reexplore
        )
