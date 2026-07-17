"""Shared types for the static verification stack.

No verifier executes the generated code. Each returns a structured
:class:`Feedback` object that the generator turns into a repair prompt.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from ..context import SymbolIndex


@dataclass
class FailureSignature:
    """Expected failure extracted from the bug report."""

    exception_type: Optional[str] = None
    message_substrings: List[str] = field(default_factory=list)
    trigger_apis: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.exception_type or self.message_substrings or self.trigger_apis)


@dataclass
class Finding:
    message: str
    line: Optional[int] = None
    suggestion: Optional[str] = None

    def render(self) -> str:
        loc = f" (line {self.line})" if self.line else ""
        text = f"- {self.message}{loc}"
        if self.suggestion:
            text += f"\n    fix: {self.suggestion}"
        return text


@dataclass
class Feedback:
    stage: str
    passed: bool
    severity: str = "error"  # "error" | "warning" | "info"
    findings: List[Finding] = field(default_factory=list)

    def render(self) -> str:
        if self.passed and not self.findings:
            return f"[{self.stage}] passed"
        header = f"[{self.stage}] {'passed' if self.passed else 'FAILED'}"
        body = "\n".join(f.render() for f in self.findings)
        return f"{header}\n{body}" if body else header

    @property
    def blocking(self) -> bool:
        return not self.passed and self.severity == "error"


@dataclass
class VerificationContext:
    """Inputs available to verifiers."""

    refined_report: str = ""
    symbol_index: SymbolIndex = field(default_factory=SymbolIndex)
    failure_signature: FailureSignature = field(default_factory=FailureSignature)
    # Optional backend for LLM-based verifiers (name, model, api_key).
    backend: Optional[object] = None


class Verifier(ABC):
    stage: str = "verifier"

    @abstractmethod
    def verify(self, code: str, ctx: VerificationContext) -> Feedback: ...
