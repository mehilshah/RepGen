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
    planner_max_tokens: int = 4096  # LLM budget for complexity planning
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
        self.planner = ExecutionPlanner(
            backend,
            self.settings.thresholds,
            max_tokens=self.settings.planner_max_tokens,
        )
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
        repo_path: Optional[Path] = None,
        hardware: Optional[HardwareInfo] = None,
        script_name: str = "reproduce.py",
    ) -> ExecutionOutcome:
        """Drive ``code`` from planning through execution/verification."""
        outcome = ExecutionOutcome()
        if not self.settings.enabled:
            outcome.error = "Execution disabled."
            return outcome

        # Resolve to an absolute path up front. Every derived path (the venv's
        # python/pip and the script) must be cwd-independent: pip install runs
        # from the process cwd while the script runs with ``cwd=run_dir``, so a
        # relative run_dir would be re-resolved against itself at run time and
        # produce a bogus, non-existent interpreter path (FileNotFoundError 127).
        run_dir = Path(run_dir).resolve()

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
        repo = Path(repo_path).resolve() if repo_path else None
        env = self._prepare_environment(run_dir, deps, resolver, fw, repo)
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
        repo_path: Optional[Path] = None,
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

        install_line = lambda line, stream: self._notify(  # noqa: E731
            "install_line", line=line, stream=stream
        )

        # 3a. Install the library under test from its checked-out source first,
        # so its declared dependencies pin the versions where the bug reproduces
        # and later detected extras don't upgrade them.
        if repo_path is not None:
            self._install_project(manager, env, repo_path, install_line)

        # 3b. Persist detected + framework deps into requirements.txt.
        req_path = run_dir / "requirements.txt"
        added = resolver.update_requirements(req_path, deps.requirements)
        self._notify("requirements_updated", path=str(req_path), added=added)

        # 3c. Install the statically-detected third-party extras. pip leaves
        # already-satisfied (repo-pinned) packages untouched — no --upgrade — so
        # this only fills gaps the repo install didn't cover.
        if deps.requirements:
            self._notify("install_start", requirements=deps.requirements)
            result = manager.install(
                env, deps.requirements, on_line=install_line
            )
            self._notify("install_done", result=result)
            if not result.success:
                self._notify(
                    "install_failed",
                    message="Dependency installation failed; execution may error.",
                )
        return env

    def _install_project(
        self,
        manager: EnvironmentManager,
        env: PreparedEnvironment,
        repo_path: Path,
        on_line: Callable[[str, str], None],
    ) -> None:
        """Install the target repo (and its own requirement pins) into ``env``.

        Prefers an editable install when the repo carries packaging metadata; if
        it does not, the repo is put on ``PYTHONPATH`` at run time instead so the
        library still imports. Either way the version matches the checked-out
        bug commit.
        """
        # Install the repo's own pinned requirements first (matching versions).
        for name in ("requirements.txt", "requirements-dev.txt"):
            req_file = repo_path / name
            if req_file.exists():
                self._notify("repo_requirements_start", file=str(req_file))
                result = manager.install_requirements_file(
                    env, req_file, on_line=on_line
                )
                self._notify("repo_requirements_done", result=result, file=str(req_file))

        if _is_packaged(repo_path):
            self._notify("project_install_start", path=str(repo_path), editable=True)
            result = manager.install_project(
                env, repo_path, on_line=on_line, editable=True
            )
            self._notify("project_install_done", result=result)
            if result.success:
                return
            # Editable install failed (build error, exotic layout): fall back to
            # PYTHONPATH so imports still resolve against the source tree.
            logger.warning("Editable install of %s failed; using PYTHONPATH.", repo_path)

        env.extra_pythonpath = str(repo_path)
        self._notify("project_on_path", path=str(repo_path))

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
        # When the repo couldn't be pip-installed, make it importable via
        # PYTHONPATH so ``import <library under test>`` resolves at run time.
        run_env = (
            {"PYTHONPATH": env.extra_pythonpath} if env.extra_pythonpath else None
        )
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
                env=run_env,
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


def _is_packaged(repo_path: Path) -> bool:
    """Whether ``repo_path`` carries packaging metadata pip can install from."""
    return any(
        (repo_path / marker).exists()
        for marker in ("pyproject.toml", "setup.py", "setup.cfg")
    )


def _merge(base: List[str], extra: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in [*base, *extra]:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
