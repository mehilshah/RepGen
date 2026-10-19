"""Bug-reproduction verification from real execution output.

After a script runs, :class:`ReproductionAnalyzer` decides whether the actual
output reproduces the reported bug. It combines two signals:

1. A cheap, offline **lexical/semantic overlap** score between the failure
   signature (exception type + distinctive message substrings) / bug report and
   the captured stdout/stderr. This works with no LLM and no extra dependencies.
2. An optional **LLM judgement** that reads the report and the output and
   returns a structured verdict with matching evidence and debugging insights.

The two are blended into a single confidence so the pipeline can report a clear
"reproduced / not reproduced" answer with supporting evidence.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional

from ..agent.verifiers.base import FailureSignature
from ..backends import LLMBackend
from ..utils import extract_json_content
from .prompts import reproduction_compare_prompt
from .runner import ExecutionResult

logger = logging.getLogger("repgen.execution.reproduction")

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


@dataclass
class ReproductionVerdict:
    """Whether execution reproduced the reported bug, and why."""

    reproduced: bool
    confidence: float
    matching_evidence: List[str] = field(default_factory=list)
    key_error: str = ""
    explanation: str = ""
    debugging_insights: List[str] = field(default_factory=list)
    signature_score: float = 0.0
    llm_used: bool = False

    def render(self) -> str:
        verdict = "REPRODUCED" if self.reproduced else "NOT reproduced"
        lines = [f"Bug {verdict} (confidence {self.confidence:.0%})"]
        if self.key_error:
            lines.append(f"Key error: {self.key_error}")
        if self.explanation:
            lines.append(self.explanation)
        for ev in self.matching_evidence:
            lines.append(f"  ✓ {ev}")
        if not self.reproduced:
            for hint in self.debugging_insights:
                lines.append(f"  → {hint}")
        return "\n".join(lines)


class ReproductionAnalyzer:
    """Compares execution output against a bug report / failure signature."""

    def __init__(
        self,
        backend: Optional[LLMBackend] = None,
        reproduced_threshold: float = 0.5,
    ):
        self.backend = backend
        self.reproduced_threshold = reproduced_threshold

    def analyze(
        self,
        result: ExecutionResult,
        bug_report: str,
        failure_signature: Optional[FailureSignature] = None,
    ) -> ReproductionVerdict:
        """Return a :class:`ReproductionVerdict` for an execution result."""
        sig_score, sig_evidence = self._signature_match(result, failure_signature)

        llm_verdict = self._llm_verdict(result, bug_report)
        if llm_verdict is not None:
            # Blend the LLM confidence with the offline signature score.
            blended = round(0.65 * llm_verdict.confidence + 0.35 * sig_score, 3)
            reproduced = llm_verdict.reproduced or (
                sig_score >= 0.8 and llm_verdict.confidence >= 0.4
            )
            evidence = _dedupe(sig_evidence + llm_verdict.matching_evidence)
            return ReproductionVerdict(
                reproduced=reproduced,
                confidence=blended,
                matching_evidence=evidence,
                key_error=llm_verdict.key_error,
                explanation=llm_verdict.explanation,
                debugging_insights=llm_verdict.debugging_insights,
                signature_score=sig_score,
                llm_used=True,
            )

        # Offline-only verdict from the signature score.
        reproduced = sig_score >= self.reproduced_threshold
        insights: List[str] = []
        if not reproduced:
            insights = self._offline_insights(result)
        return ReproductionVerdict(
            reproduced=reproduced,
            confidence=round(sig_score, 3),
            matching_evidence=sig_evidence,
            key_error=(
                f"{result.exception_type}: {result.exception_message}".strip(": ")
                if result.exception_type
                else ""
            ),
            explanation=(
                "Matched the expected failure signature."
                if reproduced
                else "Output did not match the expected failure signature."
            ),
            debugging_insights=insights,
            signature_score=sig_score,
            llm_used=False,
        )

    # -- offline signature match -----------------------------------------
    def _signature_match(
        self, result: ExecutionResult, sig: Optional[FailureSignature]
    ) -> tuple[float, List[str]]:
        output = result.combined_output
        evidence: List[str] = []
        if sig is None or sig.is_empty():
            # No structured signature: fall back to "did it raise anything?".
            if result.exception_type:
                return 0.4, [f"Raised {result.exception_type}"]
            return 0.0, []

        score = 0.0
        weight_total = 0.0

        # Exception type match (strong signal).
        if sig.exception_type:
            weight_total += 0.5
            if result.exception_type and (
                result.exception_type == sig.exception_type
                or result.exception_type.endswith("." + sig.exception_type)
            ):
                score += 0.5
                evidence.append(f"Exception type matches: {sig.exception_type}")

        # Message substrings present in output.
        if sig.message_substrings:
            weight_total += 0.4
            hit = 0
            low = output.lower()
            for sub in sig.message_substrings:
                if sub and sub.lower() in low:
                    hit += 1
                    evidence.append(f"Output contains expected text: {sub!r}")
            if sig.message_substrings:
                score += 0.4 * (hit / len(sig.message_substrings))

        # Trigger APIs appearing in the traceback/output.
        if sig.trigger_apis:
            weight_total += 0.1
            hit = 0
            for api in sig.trigger_apis:
                if api and api in output:
                    hit += 1
            if sig.trigger_apis:
                score += 0.1 * (hit / len(sig.trigger_apis))

        if weight_total == 0:
            return 0.0, evidence
        return round(score / weight_total, 3), evidence

    # -- LLM verdict ------------------------------------------------------
    def _llm_verdict(
        self, result: ExecutionResult, bug_report: str
    ) -> Optional[ReproductionVerdict]:
        if self.backend is None:
            return None
        try:
            raw = self.backend.generate(
                reproduction_compare_prompt(
                    bug_report,
                    result.stdout,
                    result.stderr,
                    result.exception_type,
                    result.traceback,
                ),
            ).text
        except Exception as e:  # noqa: BLE001
            logger.warning("Reproduction LLM call failed: %s", e)
            return None
        payload = extract_json_content(raw) or raw
        try:
            data = json.loads(payload)
        except Exception:  # noqa: BLE001
            return None
        return ReproductionVerdict(
            reproduced=bool(data.get("reproduced", False)),
            confidence=_clamp(_as_float(data.get("confidence"), 0.5)),
            matching_evidence=[
                str(e) for e in (data.get("matching_evidence") or []) if e
            ],
            key_error=str(data.get("key_error", "")),
            explanation=str(data.get("explanation", "")),
            debugging_insights=[
                str(h) for h in (data.get("debugging_insights") or []) if h
            ],
            llm_used=True,
        )

    def _offline_insights(self, result: ExecutionResult) -> List[str]:
        insights: List[str] = []
        if result.success:
            insights.append(
                "Script exited cleanly — it may not be triggering the bug path."
            )
        if result.timed_out:
            insights.append("Script timed out before producing the expected failure.")
        if result.exception_type:
            insights.append(
                f"Got {result.exception_type}, which may differ from the reported error."
            )
        return insights


def semantic_overlap(a: str, b: str) -> float:
    """Token-Jaccard blended with a difflib ratio — a light 'semantic' proxy."""
    if not a.strip() or not b.strip():
        return 0.0
    ta = set(t.lower() for t in _TOKEN_RE.findall(a))
    tb = set(t.lower() for t in _TOKEN_RE.findall(b))
    if not ta or not tb:
        jaccard = 0.0
    else:
        jaccard = len(ta & tb) / len(ta | tb)
    ratio = SequenceMatcher(None, a[:2000], b[:2000]).ratio()
    return round(0.5 * jaccard + 0.5 * ratio, 3)


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))
