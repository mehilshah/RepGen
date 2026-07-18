"""Stage 2: compilation checks.

Compiles the source to bytecode (``compile``) and runs an optional, focused
``pylint`` pass for binding errors. Nothing is executed: ``compile`` only parses
and builds a code object, and ``pylint`` is a static analyzer.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import Feedback, Finding, VerificationContext, Verifier

logger = logging.getLogger("repgen.agent.verifiers")

# Binding errors that do not depend on third-party packages being installed
# (so we avoid false positives like import-error for an uninstalled `torch`).
_PYLINT_CHECKS = "undefined-variable,used-before-assignment"


class CompilationVerifier(Verifier):
    stage = "compilation"

    def __init__(self, use_pylint: bool = True):
        self.use_pylint = use_pylint

    def verify(self, code: str, ctx: VerificationContext) -> Feedback:
        findings = []
        try:
            compile(code, "<repgen-generated>", "exec")
        except SyntaxError as e:
            # Should be caught earlier, but keep the stage self-contained.
            findings.append(
                Finding(message=f"Does not compile: {e.msg}", line=e.lineno)
            )
            return Feedback(stage=self.stage, passed=False, findings=findings)

        if self.use_pylint:
            findings.extend(self._pylint(code))

        passed = not findings
        return Feedback(stage=self.stage, passed=passed, findings=findings)

    def _pylint(self, code: str) -> list[Finding]:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                tmp_path = f.name
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pylint",
                    "--disable=all",
                    f"--enable={_PYLINT_CHECKS}",
                    "--output-format=json",
                    tmp_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            messages = json.loads(proc.stdout or "[]")
        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
            OSError,
        ) as e:
            logger.info("pylint pass skipped: %s", e)
            return []
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

        findings = []
        for m in messages:
            findings.append(
                Finding(
                    message=f"{m.get('symbol', m.get('message-id'))}: {m.get('message')}",
                    line=m.get("line"),
                    suggestion="Define the name or fix the reference before use.",
                )
            )
        return findings
