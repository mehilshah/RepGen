"""Tests for the bug-reproduction analyzer."""

from __future__ import annotations

from repgen.agent.verifiers.base import FailureSignature
from repgen.execution.reproduction import (
    ReproductionAnalyzer,
    semantic_overlap,
)
from repgen.execution.runner import ExecutionResult


def _result(stdout="", stderr="", exc=None, msg="", tb="", rc=1):
    return ExecutionResult(
        returncode=rc,
        stdout=stdout,
        stderr=stderr,
        exception_type=exc,
        exception_message=msg,
        traceback=tb,
    )


def test_offline_signature_match_reproduced():
    sig = FailureSignature(
        exception_type="ValueError", message_substrings=["boom xyz"]
    )
    result = _result(
        stderr="Traceback...\nValueError: boom xyz",
        exc="ValueError",
        msg="boom xyz",
    )
    verdict = ReproductionAnalyzer(backend=None).analyze(result, "bug", sig)
    assert verdict.reproduced
    assert verdict.confidence >= 0.5
    assert not verdict.llm_used
    assert verdict.matching_evidence


def test_offline_no_match_gives_insights():
    sig = FailureSignature(exception_type="KeyError", message_substrings=["missing"])
    result = _result(stdout="all good", rc=0, exc=None)
    result.returncode = 0
    verdict = ReproductionAnalyzer(backend=None).analyze(result, "bug", sig)
    assert not verdict.reproduced
    assert verdict.debugging_insights


def test_llm_verdict_blended():
    class B:
        def generate(self, prompt, **kw):
            class R:
                text = (
                    '{"reproduced":true,"confidence":0.9,'
                    '"matching_evidence":["ValueError"],"key_error":"ValueError",'
                    '"explanation":"matches","debugging_insights":[]}'
                )
            return R()

    sig = FailureSignature(exception_type="ValueError", message_substrings=["boom"])
    result = _result(stderr="ValueError: boom", exc="ValueError", msg="boom")
    verdict = ReproductionAnalyzer(backend=B()).analyze(result, "bug", sig)
    assert verdict.reproduced
    assert verdict.llm_used
    assert 0.0 <= verdict.confidence <= 1.0


def test_semantic_overlap_bounds():
    assert semantic_overlap("", "") == 0.0
    assert semantic_overlap("hello world", "hello world") > 0.9
    assert 0.0 <= semantic_overlap("a b c", "x y z") <= 1.0


def test_empty_signature_uses_exception_presence():
    result = _result(stderr="RuntimeError: x", exc="RuntimeError", msg="x")
    verdict = ReproductionAnalyzer(backend=None).analyze(result, "bug", FailureSignature())
    assert verdict.signature_score > 0
