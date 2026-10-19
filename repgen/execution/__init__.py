"""Execution engine for RepGen.

This package adds the runtime side of RepGen: after the exploration/generation
pipeline produces a candidate script (in :mod:`repgen.agent`), the execution
engine can plan, prepare an isolated environment, install dependencies, run the
code with live output, verify whether a bug reproduced, and refine/retry on
failure.

It is intentionally decoupled from the static verification stack in
:mod:`repgen.agent.verifiers` — static checks act as a pre-execution gate, and
this package layers real execution on top. Everything here communicates through
plain dataclasses and progress/confirm callbacks (mirroring the existing
``progress_callback`` pattern in :class:`repgen.core.RepGenService`) so the UI in
:mod:`repgen.ui` and :mod:`repgen.reporting` can render it however it likes.
"""

from __future__ import annotations

from .dependencies import (
    DependencyReport,
    DependencyResolver,
)
from .environment import EnvironmentManager, PreparedEnvironment
from .hardware import HardwareInfo, detect_hardware
from .pipeline import ExecutionOutcome, ExecutionPipeline
from .planner import Complexity, ExecutionPlan, ExecutionPlanner
from .reproduction import ReproductionAnalyzer, ReproductionVerdict
from .runner import CodeRunner, ExecutionResult

__all__ = [
    "Complexity",
    "CodeRunner",
    "DependencyReport",
    "DependencyResolver",
    "EnvironmentManager",
    "ExecutionOutcome",
    "ExecutionPipeline",
    "ExecutionPlan",
    "ExecutionPlanner",
    "ExecutionResult",
    "HardwareInfo",
    "PreparedEnvironment",
    "ReproductionAnalyzer",
    "ReproductionVerdict",
    "detect_hardware",
]
