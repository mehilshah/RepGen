"""Stage 1: syntax verification via ``ast.parse``.

Fixes the historical bug where a ``SyntaxError`` was reported as "passed".
"""

from __future__ import annotations

import ast

from .base import Feedback, Finding, VerificationContext, Verifier

# Node types that make a script an actual reproduction (imports the code under
# test, calls into it, defines/asserts something) rather than a no-op.
_SUBSTANTIVE = (
    ast.Import,
    ast.ImportFrom,
    ast.Call,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.For,
    ast.While,
    ast.With,
    ast.If,
    ast.Raise,
    ast.Assert,
)


def _has_substance(tree: ast.AST) -> bool:
    """True if the script contains at least one runnable statement.

    An empty string, whitespace, or a bare ``pass`` / docstring parses cleanly,
    so without this check a model that returns *nothing* (e.g. a reasoning model
    that spent its whole budget thinking) would vacuously pass every static
    stage and be reported as a verified reproduction.
    """
    return any(isinstance(node, _SUBSTANTIVE) for node in ast.walk(tree))


class SyntaxVerifier(Verifier):
    stage = "syntax"

    def verify(self, code: str, ctx: VerificationContext) -> Feedback:
        try:
            tree = ast.parse(code)
            if not _has_substance(tree):
                finding = Finding(
                    message="The script is empty or has no runnable statements "
                    "(the model returned no usable code).",
                    suggestion="Output a complete Python reproduction script that "
                    "imports the code under test and triggers the bug.",
                )
                return Feedback(stage=self.stage, passed=False, findings=[finding])
            return Feedback(stage=self.stage, passed=True)
        except SyntaxError as e:
            text = (e.text or "").strip()
            finding = Finding(
                message=f"SyntaxError: {e.msg}" + (f" near '{text}'" if text else ""),
                line=e.lineno,
                suggestion="Produce syntactically valid Python.",
            )
            return Feedback(stage=self.stage, passed=False, findings=[finding])
