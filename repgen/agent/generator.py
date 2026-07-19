"""Feedback-driven reproduction generator (plan → code → verify → repair)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from ..backends import LLMBackend
from ..prompts import code_prompt, plan_prompt
from ..utils import extract_json_content
from .context import RetrievedContext
from .explorer import ExplorationAgent
from .feedback import FeedbackPipeline, VerificationResult, extract_failure_signature
from .verifiers import FailureSignature, VerificationContext

logger = logging.getLogger("repgen.agent.generator")

ProgressCb = Optional[Callable[[str, dict], None]]


@dataclass
class Attempt:
    index: int
    code: str
    result: VerificationResult


@dataclass
class GenerationResult:
    success: bool
    code: Optional[str] = None
    plan: str = ""
    attempts: List[Attempt] = field(default_factory=list)
    failure_signature: Optional[FailureSignature] = None


class ReproductionGenerator:
    def __init__(
        self,
        backend: LLMBackend,
        pipeline: Optional[FeedbackPipeline] = None,
        progress_cb: ProgressCb = None,
    ):
        self.backend = backend
        self.pipeline = pipeline or FeedbackPipeline()
        self.progress_cb = progress_cb

    def _notify(self, event: str, **data: Any) -> None:
        if self.progress_cb:
            self.progress_cb(event, data)

    def _make_plan(self, refined_report: str, context: RetrievedContext) -> str:
        raw = self.backend.generate(
            plan_prompt(refined_report, context.as_prompt_text())
        ).text
        plan = extract_json_content(raw) or raw
        try:  # normalize to a readable bullet list if it is a JSON array
            steps = json.loads(plan)
            if isinstance(steps, list):
                plan = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        except Exception:  # noqa: BLE001
            pass
        self._notify("plan", plan=plan)
        return plan

    def generate(
        self,
        refined_report: str,
        context: RetrievedContext,
        max_attempts: int = 3,
        explorer: Optional[ExplorationAgent] = None,
    ) -> GenerationResult:
        failure_sig = extract_failure_signature(refined_report, self.backend)
        self._notify("failure_signature", signature=failure_sig)

        plan = self._make_plan(refined_report, context)
        result = GenerationResult(
            success=False, plan=plan, failure_signature=failure_sig
        )
        feedback_text: Optional[str] = None
        best: Optional[Attempt] = None

        for attempt_no in range(1, max_attempts + 1):
            self._notify("attempt_start", attempt=attempt_no, total=max_attempts)

            # No fixed output cap: generation inherits the user's effort tier so
            # a reasoning model isn't starved of output tokens by its own
            # thinking (the cause of empty, "vacuously verified" scripts).
            raw_code = self.backend.generate(
                code_prompt(
                    refined_report,
                    context.as_prompt_text(),
                    plan,
                    feedback=feedback_text,
                ),
            ).text
            code = extract_json_content(raw_code) or raw_code

            vctx = VerificationContext(
                refined_report=refined_report,
                symbol_index=context.symbol_index,
                failure_signature=failure_sig,
                backend=self.backend,
            )
            verification = self.pipeline.run(code, vctx)
            attempt = Attempt(attempt_no, code, verification)
            result.attempts.append(attempt)
            best = attempt
            self._notify(
                "attempt_verified",
                attempt=attempt_no,
                passed=verification.passed,
                feedbacks=verification.feedbacks,
            )

            if verification.passed:
                result.success = True
                result.code = code
                return result

            feedback_text = verification.repair_text()

            # Closed loop: if a symbol could not be resolved, gather more context.
            if verification.needs_reexploration and explorer is not None:
                self._notify("reexplore", attempt=attempt_no)
                hint = (
                    "A previous reproduction attempt referenced symbols that could "
                    "not be resolved. Find the correct import paths / signatures for:\n"
                    + feedback_text
                )
                context = explorer.explore(refined_report + "\n\n" + hint)
                plan = self._make_plan(refined_report, context)

        # No attempt passed; return the last one as the best effort.
        if best is not None:
            result.code = best.code
        return result
