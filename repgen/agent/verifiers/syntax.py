"""Stage 1: syntax verification via ``ast.parse``.

Fixes the historical bug where a ``SyntaxError`` was reported as "passed".
"""

from __future__ import annotations

import ast

from .base import Feedback, Finding, VerificationContext, Verifier


class SyntaxVerifier(Verifier):
    stage = "syntax"

    def verify(self, code: str, ctx: VerificationContext) -> Feedback:
        try:
            ast.parse(code)
            return Feedback(stage=self.stage, passed=True)
        except SyntaxError as e:
            text = (e.text or "").strip()
            finding = Finding(
                message=f"SyntaxError: {e.msg}" + (f" near '{text}'" if text else ""),
                line=e.lineno,
                suggestion="Produce syntactically valid Python.",
            )
            return Feedback(stage=self.stage, passed=False, findings=[finding])
