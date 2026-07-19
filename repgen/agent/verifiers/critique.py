"""Stage 4: structured LLM critique (replaces the old yes/no relevance check)."""

from __future__ import annotations

import json
import logging
from typing import Optional

from ...prompts import critique_prompt
from ...utils import extract_json_content
from .base import Feedback, Finding, VerificationContext, Verifier

logger = logging.getLogger("repgen.agent.verifiers")


class CritiqueVerifier(Verifier):
    stage = "critique"

    def verify(self, code: str, ctx: VerificationContext) -> Feedback:
        backend = ctx.backend
        if backend is None:
            return Feedback(stage=self.stage, passed=True, severity="info")

        raw = backend.generate(
            critique_prompt(ctx.refined_report, code)
        ).text
        payload = self._parse(raw)
        if payload is None:
            # Non-blocking: don't fail a run because the judge misbehaved.
            return Feedback(
                stage=self.stage,
                passed=True,
                severity="warning",
                findings=[Finding(message="Could not parse critique response.")],
            )

        reproduces = bool(payload.get("reproduces"))
        issues = payload.get("issues") or []
        findings = [Finding(message=str(i)) for i in issues if str(i).strip()]
        if reproduces:
            return Feedback(stage=self.stage, passed=True, findings=findings)
        if not findings:
            findings = [
                Finding(
                    message=str(payload.get("reasoning", "Judged not to reproduce."))
                )
            ]
        return Feedback(stage=self.stage, passed=False, findings=findings)

    @staticmethod
    def _parse(raw: str) -> Optional[dict]:
        for candidate in (extract_json_content(raw) or "", raw):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except Exception:  # noqa: BLE001
                continue
        return None
