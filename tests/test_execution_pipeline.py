"""Tests for the end-to-end execution pipeline (no network, no real LLM)."""

from __future__ import annotations

from repgen.agent.verifiers.base import FailureSignature
from repgen.backends.base import LLMBackend, LLMResponse
from repgen.execution.pipeline import (
    ExecutionDecision,
    ExecutionPipeline,
    ExecutionSettings,
)


class PlannerBackend(LLMBackend):
    """Answers planner + reproduction prompts; used for pipeline tests."""

    name = "planner"
    default_model = "planner-1"

    def __init__(self, reproduced=True, complexity="quick", refine_to=None):
        super().__init__("planner-1")
        self.reproduced = reproduced
        self.complexity = complexity
        self.refine_to = refine_to

    def generate(self, prompt, **kw):
        if "execution-planning" in prompt:
            return LLMResponse(
                text=f'{{"complexity":"{self.complexity}","estimated_minutes":1,'
                '"confidence":0.9,"needs_gpu":false,"peak_ram_gb":0.1,'
                '"disk_gb":0.1,"rationale":"t","risks":[]}'
            )
        if "reproduces a reported bug" in prompt:
            rep = "true" if self.reproduced else "false"
            return LLMResponse(
                text=f'{{"reproduced":{rep},"confidence":0.9,'
                '"matching_evidence":["x"],"key_error":"e","explanation":"y",'
                '"debugging_insights":["retry"]}'
            )
        if "failed to execute" in prompt and self.refine_to:
            return LLMResponse(text=f"root cause\n```python\n{self.refine_to}\n```")
        return LLMResponse(text="")


def _pipeline(backend, **settings):
    return ExecutionPipeline(backend, ExecutionSettings(**settings))


def test_quick_auto_executes_and_reproduces(tmp_path):
    code = "print('repro')\nraise ValueError('boom')\n"
    pipe = _pipeline(PlannerBackend(reproduced=True), max_retries=0)
    out = pipe.run(
        code, run_dir=tmp_path / "run", goal="reproduce boom",
        bug_report="ValueError boom",
        failure_signature=FailureSignature(exception_type="ValueError"),
    )
    assert out.executed
    assert out.decision is ExecutionDecision.EXECUTE
    assert out.reproduced
    assert len(out.attempts) == 1
    assert (tmp_path / "run" / ".venv").exists()


def test_medium_skipped_without_confirm(tmp_path):
    pipe = _pipeline(PlannerBackend(complexity="medium"), max_retries=0)
    out = pipe.run(
        "print('x')\n", run_dir=tmp_path / "run", goal="g", bug_report="b",
    )
    # No confirm callback => non-interactive policy skips non-quick runs.
    assert out.decision is ExecutionDecision.SKIP
    assert not out.executed


def test_confirm_prepare_only(tmp_path):
    def confirm(plan, hw):
        return ExecutionDecision.PREPARE_ONLY

    pipe = ExecutionPipeline(
        PlannerBackend(complexity="large"),
        ExecutionSettings(max_retries=0),
        confirm_cb=confirm,
    )
    out = pipe.run("print('x')\n", run_dir=tmp_path / "run", goal="g", bug_report="")
    assert out.decision is ExecutionDecision.PREPARE_ONLY
    assert not out.executed
    assert (tmp_path / "run" / "run_commands.sh").exists()


def test_repro_that_raises_is_not_refined_away(tmp_path):
    # Bug reproduction that raises exits non-zero but reproduces -> done, 1 attempt.
    code = "raise ValueError('boom')\n"
    pipe = _pipeline(
        PlannerBackend(reproduced=True, refine_to="print('fixed')"), max_retries=2
    )
    out = pipe.run(
        code, run_dir=tmp_path / "run", goal="g", bug_report="ValueError boom",
        failure_signature=FailureSignature(exception_type="ValueError"),
    )
    assert out.reproduced
    assert len(out.attempts) == 1  # not refined despite non-zero exit


def test_refine_retry_on_incidental_error(tmp_path):
    # First run hits an ImportError (not the bug); refine to a version that raises
    # the expected error -> reproduced on the second attempt.
    code = "import definitely_missing_pkg_xyz\n"
    refined = "raise ValueError('boom')\n"
    pipe = _pipeline(
        PlannerBackend(reproduced=False, refine_to=refined), max_retries=2
    )

    # Make the analyzer reproduce only when the ValueError is present by using a
    # signature; the LLM says not reproduced first, but signature carries it.
    out = pipe.run(
        code, run_dir=tmp_path / "run", goal="g", bug_report="ValueError boom",
        failure_signature=FailureSignature(exception_type="ValueError"),
    )
    assert len(out.attempts) >= 2
    assert out.attempts[0].refined


def test_disabled_pipeline_returns_early(tmp_path):
    pipe = _pipeline(PlannerBackend(), enabled=False)
    out = pipe.run("print('x')\n", run_dir=tmp_path / "run", goal="g", bug_report="")
    assert not out.executed
    assert out.error
