"""End-to-end execution pipeline: plan → prepare → run → verify → refine.

:class:`ExecutionPipeline` is the runtime counterpart of
:class:`repgen.agent.generator.ReproductionGenerator`. It takes a candidate
script and drives it all the way to an execution verdict, applying the
complexity gating the user asked for:

* **Quick** — prepare + run automatically.
* **Medium** — surface the estimate and ask the user whether to proceed.
* **Large** — surface a detailed estimate and let the user choose to execute,
  only prepare the environment, or skip.

On failure it can ask the LLM to analyze logs/errors, refine the script, and
retry up to a configurable limit. All feedback flows through a
``progress_callback`` (event, data) mirroring :class:`repgen.core.RepGenService`,
so the UI layer decides how to render it. Confirmation is delegated to a
``confirm_callback`` so the pipeline stays UI-agnostic and testable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Optional

from ..agent.verifiers.base import FailureSignature
from ..backends import LLMBackend
from ..utils import extract_json_content
from .dependencies import DependencyReport, DependencyResolver
from .environment import EnvironmentManager, PreparedEnvironment
from .frameworks import Framework, get_framework
from .hardware import HardwareInfo, detect_hardware
from .planner import Complexity, ComplexityThresholds, ExecutionPlan, ExecutionPlanner
from .prompts import refine_prompt
from .reproduction import ReproductionAnalyzer, ReproductionVerdict
from .runner import CodeRunner, ExecutionResult

logger = logging.getLogger("repgen.execution.pipeline")

ProgressCb = Optional[Callable[[str, dict], None]]


class ExecutionDecision(str, Enum):
    """What the user (or policy) chose to do with a planned execution."""

    EXECUTE = "execute"
    PREPARE_ONLY = "prepare_only"
    SKIP = "skip"


# Confirmation callback: given the plan + hardware, return a decision.
ConfirmCb = Optional[Callable[[ExecutionPlan, HardwareInfo], ExecutionDecision]]


@dataclass
class ExecutionSettings:
    """Tunables for the execution pipeline (sourced from RepGenConfig/CLI)."""

    enabled: bool = True
    max_retries: int = 2  # refine/retry attempts after the first run
    quick_timeout_s: int = 900  # 15 min
    medium_timeout_s: int = 2700  # 45 min
    large_timeout_s: int = 5400  # 90 min
    auto_execute_quick: bool = True
    system_site_packages: bool = False
    reproduced_threshold: float = 0.5
    thresholds: ComplexityThresholds = field(default_factory=ComplexityThresholds)

    def timeout_for(self, complexity: Complexity, plan_minutes: float) -> int:
        base = {
            Complexity.QUICK: self.quick_timeout_s,
            Complexity.MEDIUM: self.medium_timeout_s,
            Complexity.LARGE: self.large_timeout_s,
        }[complexity]
        # Never allot less than ~2x the estimate.
        return max(base, int(plan_minutes * 60 * 2))


@dataclass
class ExecutionAttempt:
    """One run of the code, plus its verdict and any refinement applied after."""

    index: int
    code: str
    result: ExecutionResult
    verdict: Optional[ReproductionVerdict] = None
    refined: bool = False
    root_cause: str = ""


@dataclass
class ExecutionOutcome:
    """The full result of running the pipeline over a script."""

    executed: bool = False
    decision: ExecutionDecision = ExecutionDecision.SKIP
    plan: Optional[ExecutionPlan] = None
    hardware: Optional[HardwareInfo] = None
    dependencies: Optional[DependencyReport] = None
    environment: Optional[PreparedEnvironment] = None
    attempts: List[ExecutionAttempt] = field(default_factory=list)
    final_code: Optional[str] = None
    reproduced: bool = False
    error: Optional[str] = None

    @property
    def last_attempt(self) -> Optional[ExecutionAttempt]:
        return self.attempts[-1] if self.attempts else None

    @property
    def succeeded(self) -> bool:
        last = self.last_attempt
        return bool(last and last.result.success)


class ExecutionPipeline:
    """Plans, prepares, runs, verifies and refines a generated script."""

    def __init__(
        self,
        backend: Optional[LLMBackend],
        settings: Optional[ExecutionSettings] = None,
        *,
        progress_cb: ProgressCb = None,
        confirm_cb: ConfirmCb = None,
    ):
        self.backend = backend
        self.settings = settings or ExecutionSettings()
        self.progress_cb = progress_cb
        self.confirm_cb = confirm_cb
        self.planner = ExecutionPlanner(backend, self.settings.thresholds)
        self.analyzer = ReproductionAnalyzer(
            backend, self.settings.reproduced_threshold
        )

    def _notify(self, event: str, **data: Any) -> None:
        if self.progress_cb:
            self.progress_cb(event, data)

    # -- public API -------------------------------------------------------
    def run(
        self,
        code: str,
        *,
        run_dir: Path,
        goal: str,
        bug_report: str = "",
        failure_signature: Optional[FailureSignature] = None,
        framework: Optional[str] = None,
        local_modules: Optional[List[str]] = None,
        hardware: Optional[HardwareInfo] = None,
        script_name: str = "reproduce.py",
    ) -> ExecutionOutcome:
        """Drive ``code`` from planning through execution/verification."""
        outcome = ExecutionOutcome()
        if not self.settings.enabled:
            outcome.error = "Execution disabled."
            return outcome

        fw = get_framework(framework)
        hw = hardware or detect_hardware(str(run_dir))
        outcome.hardware = hw
        self._notify("hardware", info=hw)

        resolver = DependencyResolver(local_modules=local_modules)
        deps = resolver.resolve(code)
        # Framework base dependencies are always part of the environment.
        deps.requirements = _merge(fw.dependencies, deps.requirements)
        outcome.dependencies = deps
        self._notify("dependencies", report=deps)

        # 1. Plan.
        plan = self.planner.plan(code, deps, hw, bug_report or None)
        outcome.plan = plan
        self._notify("plan", plan=plan)

        # 2. Gate on complexity.
        decision = self._decide(plan, hw)
        outcome.decision = decision
        self._notify("decision", decision=decision.value, plan=plan)
        if decision is ExecutionDecision.SKIP:
            outcome.final_code = code
            return outcome

        # 3. Prepare environment + install deps.
        run_dir.mkdir(parents=True, exist_ok=True)
        env = self._prepare_environment(run_dir, deps, resolver, fw)
        outcome.environment = env
        if env is None:
            outcome.error = "Failed to prepare environment."
            return outcome

        if decision is ExecutionDecision.PREPARE_ONLY:
            self._notify("prepare_only", env=env)
            outcome.final_code = code
            self._write_commands(run_dir, env, fw, script_name)
            return outcome

        # 4. Execute with refine/retry loop.
        outcome.executed = True
        self._execute_loop(
            code, outcome, run_dir, env, fw, goal, bug_report,
            failure_signature, plan, script_name,
        )
        return outcome

    # -- gating -----------------------------------------------------------
    def _decide(self, plan: ExecutionPlan, hw: HardwareInfo) -> ExecutionDecision:
        if plan.complexity is Complexity.QUICK:
            if self.settings.auto_execute_quick:
                return ExecutionDecision.EXECUTE
            # Fall through to confirmation when auto-run is disabled.

        if self.confirm_cb is None:
            # Non-interactive policy: run quick automatically, skip heavier runs.
            return (
                ExecutionDecision.EXECUTE
                if plan.complexity is Complexity.QUICK
                else ExecutionDecision.SKIP
            )
        try:
            return self.confirm_cb(plan, hw)
        except Exception as e:  # noqa: BLE001 - never let confirmation crash a run
            logger.warning("confirm callback failed: %s", e)
            return ExecutionDecision.SKIP

    # -- environment ------------------------------------------------------
    def _prepare_environment(
        self,
        run_dir: Path,
        deps: DependencyReport,
        resolver: DependencyResolver,
        fw: Framework,
    ) -> Optional[PreparedEnvironment]:
        self._notify("env_prepare_start", run_dir=str(run_dir))
        manager = EnvironmentManager(
            run_dir, system_site_packages=self.settings.system_site_packages
        )
        try:
            env = manager.prepare(
                on_line=lambda line, stream: self._notify(
                    "env_line", line=line, stream=stream
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("venv creation failed")
            self._notify("env_error", message=str(e))
            return None

        # Persist detected + framework deps into requirements.txt.
        req_path = run_dir / "requirements.txt"
        added = resolver.update_requirements(req_path, deps.requirements)
        self._notify("requirements_updated", path=str(req_path), added=added)

        if deps.requirements:
            self._notify("install_start", requirements=deps.requirements)
            result = manager.install(
                env,
                deps.requirements,
                on_line=lambda line, stream: self._notify(
                    "install_line", line=line, stream=stream
                ),
            )
            self._notify("install_done", result=result)
            if not result.success:
                self._notify(
                    "install_failed",
                    message="Dependency installation failed; execution may error.",
                )
        return env

    def _write_commands(
        self,
        run_dir: Path,
        env: PreparedEnvironment,
        fw: Framework,
        script_name: str,
    ) -> None:
        """Write a runnable commands cheat-sheet for prepare-only runs."""
        script = run_dir / script_name
        lines = [
            "# RepGen environment commands",
            "",
            "# Create the virtual environment:",
            " ".join(env.setup_command()),
            "",
            "# Install dependencies:",
            f"{env.pip} install -r {run_dir / 'requirements.txt'}",
            "",
            "# Run:",
            " ".join(fw.run_command(str(env.python), str(script))),
            "",
        ]
        (run_dir / "run_commands.sh").write_text("\n".join(lines))

    # -- execute + refine/retry ------------------------------------------
    def _execute_loop(
        self,
        code: str,
        outcome: ExecutionOutcome,
        run_dir: Path,
        env: PreparedEnvironment,
        fw: Framework,
        goal: str,
        bug_report: str,
        failure_signature: Optional[FailureSignature],
        plan: ExecutionPlan,
        script_name: str,
    ) -> None:
        runner = CodeRunner(env.python)
        timeout = self.settings.timeout_for(plan.complexity, plan.estimated_minutes)
        current = code

        total = self.settings.max_retries + 1
        for attempt_no in range(1, total + 1):
            script_path = run_dir / script_name
            script_path.write_text(current)
            self._notify(
                "exec_start",
                attempt=attempt_no,
                total=total,
                command=fw.run_command(str(env.python), str(script_path)),
                timeout=timeout,
            )
            start = time.time()
            result = runner.run(
                script_path,
                cwd=run_dir,
                timeout=timeout,
                on_line=lambda line, stream: self._notify(
                    "exec_line", line=line, stream=stream, attempt=attempt_no
                ),
            )
            self._notify("exec_done", attempt=attempt_no, result=result,
                         elapsed=time.time() - start)

            verdict = self.analyzer.analyze(result, bug_report, failure_signature)
            self._notify("verdict", attempt=attempt_no, verdict=verdict)

            attempt = ExecutionAttempt(
                index=attempt_no, code=current, result=result, verdict=verdict
            )
            outcome.attempts.append(attempt)
            outcome.final_code = current
            outcome.reproduced = verdict.reproduced

            # Done criterion:
            #  - Bug-reproduction mode: the run reproduced the reported failure.
            #    A repro script that raises the expected exception exits non-zero,
            #    so we must NOT require a clean exit here.
            #  - Plain code-gen mode: the script ran cleanly.
            if bug_report:
                done = verdict.reproduced
            else:
                done = result.success
            if done or attempt_no == total:
                if not done:
                    self._notify("retries_exhausted", attempt=attempt_no)
                return

            # Refine and retry.
            refined, cause = self._refine(current, result, goal)
            attempt.root_cause = cause
            if refined is None or refined.strip() == current.strip():
                self._notify("refine_noop", attempt=attempt_no)
                return
            attempt.refined = True
            self._notify("refine", attempt=attempt_no, root_cause=cause)
            current = refined

    def _refine(
        self, code: str, result: ExecutionResult, goal: str
    ) -> tuple[Optional[str], str]:
        """Ask the LLM to analyze the failure and return corrected code."""
        if self.backend is None:
            return None, ""
        try:
            raw = self.backend.generate(
                refine_prompt(
                    code,
                    result.stdout,
                    result.stderr,
                    result.exception_type,
                    result.traceback,
                    goal,
                ),
                max_tokens=4096,
            ).text
        except Exception as e:  # noqa: BLE001
            logger.warning("refine LLM call failed: %s", e)
            return None, ""
        # The prompt asks for a one-line root cause then a fenced code block.
        cause = ""
        for line in raw.splitlines():
            if line.strip():
                cause = line.strip().lstrip("#").strip()
                break
        refined = extract_json_content(raw)
        return refined, cause


def _merge(base: List[str], extra: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in [*base, *extra]:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
