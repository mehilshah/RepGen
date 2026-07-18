"""LLM-driven execution planner.

Combines the detected :class:`~repgen.execution.hardware.HardwareInfo` with an
LLM estimate of how heavy a script is, and classifies the run as ``QUICK``,
``MEDIUM`` or ``LARGE``. The pipeline uses this to decide whether to run
automatically, ask the user to confirm, or offer a prepare-only/skip choice.

The LLM is best-effort: if it is unavailable or returns garbage we fall back to
a cheap static heuristic so the pipeline always has a plan.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from ..backends import LLMBackend
from ..utils import extract_json_content
from .dependencies import DependencyReport
from .hardware import HardwareInfo
from .prompts import planner_prompt

logger = logging.getLogger("repgen.execution.planner")

# Heavy packages that strongly suggest a non-trivial run when detected.
_HEAVY_PACKAGES = {
    "torch", "tensorflow", "jax", "transformers", "datasets", "keras",
    "xgboost", "lightgbm", "spacy", "detectron2", "mmcv", "vllm",
}


class Complexity(str, Enum):
    QUICK = "quick"
    MEDIUM = "medium"
    LARGE = "large"

    @property
    def label(self) -> str:
        return {"quick": "Quick", "medium": "Medium", "large": "Large"}[self.value]


@dataclass
class ComplexityThresholds:
    """Minute boundaries between the three buckets (inclusive of lower bound)."""

    quick_max_minutes: float = 10.0
    medium_max_minutes: float = 40.0

    def classify(self, minutes: float) -> Complexity:
        if minutes <= self.quick_max_minutes:
            return Complexity.QUICK
        if minutes <= self.medium_max_minutes:
            return Complexity.MEDIUM
        return Complexity.LARGE


@dataclass
class ExecutionPlan:
    """The planner's assessment of a script + environment."""

    complexity: Complexity
    estimated_minutes: float
    confidence: float = 0.5
    needs_gpu: bool = False
    peak_ram_gb: float = 0.0
    disk_gb: float = 0.0
    rationale: str = ""
    risks: List[str] = field(default_factory=list)
    source: str = "llm"  # "llm" | "heuristic"

    @property
    def gpu_shortfall(self) -> bool:
        """Needs a GPU that the plan flags but the host may lack (set by planner)."""
        return getattr(self, "_gpu_shortfall", False)

    def render(self) -> str:
        lines = [
            f"Complexity: {self.complexity.label}",
            f"Estimated runtime: ~{self.estimated_minutes:.0f} min "
            f"(confidence {self.confidence:.0%})",
        ]
        if self.needs_gpu:
            lines.append("Requires GPU: yes")
        if self.peak_ram_gb:
            lines.append(f"Peak RAM: ~{self.peak_ram_gb:.1f} GB")
        if self.disk_gb:
            lines.append(f"Disk: ~{self.disk_gb:.1f} GB")
        if self.rationale:
            lines.append(f"Rationale: {self.rationale}")
        for risk in self.risks:
            lines.append(f"Risk: {risk}")
        return "\n".join(lines)


class ExecutionPlanner:
    """Estimates execution complexity using an LLM + hardware context."""

    def __init__(
        self,
        backend: Optional[LLMBackend] = None,
        thresholds: Optional[ComplexityThresholds] = None,
    ):
        self.backend = backend
        self.thresholds = thresholds or ComplexityThresholds()

    def plan(
        self,
        code: str,
        dependencies: DependencyReport,
        hardware: HardwareInfo,
        bug_report: Optional[str] = None,
    ) -> ExecutionPlan:
        """Produce an :class:`ExecutionPlan` for ``code``."""
        plan = self._llm_plan(code, dependencies, hardware, bug_report)
        if plan is None:
            plan = self._heuristic_plan(code, dependencies, hardware)
        # Flag a GPU shortfall: the plan needs a GPU but none was detected.
        if plan.needs_gpu and not hardware.has_gpu:
            plan._gpu_shortfall = True  # type: ignore[attr-defined]
            if "No GPU detected; CPU fallback may be very slow" not in plan.risks:
                plan.risks.append("No GPU detected; CPU fallback may be very slow")
            # A missing GPU pushes the run toward the LARGE bucket.
            if plan.complexity == Complexity.QUICK:
                plan.complexity = Complexity.MEDIUM
        return plan

    # -- LLM path ---------------------------------------------------------
    def _llm_plan(
        self,
        code: str,
        dependencies: DependencyReport,
        hardware: HardwareInfo,
        bug_report: Optional[str],
    ) -> Optional[ExecutionPlan]:
        if self.backend is None:
            return None
        try:
            raw = self.backend.generate(
                planner_prompt(
                    code,
                    ", ".join(dependencies.requirements),
                    hardware.render(),
                    bug_report,
                ),
                max_tokens=600,
            ).text
        except Exception as e:  # noqa: BLE001
            logger.warning("Planner LLM call failed: %s", e)
            return None
        payload = extract_json_content(raw) or raw
        try:
            data = json.loads(payload)
        except Exception:  # noqa: BLE001
            logger.debug("Planner returned non-JSON; falling back to heuristic.")
            return None

        minutes = _as_float(data.get("estimated_minutes"), default=5.0)
        # Trust the LLM's bucket if valid, else derive from minutes.
        raw_complexity = str(data.get("complexity", "")).lower()
        try:
            complexity = Complexity(raw_complexity)
        except ValueError:
            complexity = self.thresholds.classify(minutes)
        return ExecutionPlan(
            complexity=complexity,
            estimated_minutes=minutes,
            confidence=_as_float(data.get("confidence"), 0.5),
            needs_gpu=bool(data.get("needs_gpu", False)),
            peak_ram_gb=_as_float(data.get("peak_ram_gb"), 0.0),
            disk_gb=_as_float(data.get("disk_gb"), 0.0),
            rationale=str(data.get("rationale", "")),
            risks=[str(r) for r in (data.get("risks") or []) if r],
            source="llm",
        )

    # -- Heuristic fallback ----------------------------------------------
    def _heuristic_plan(
        self,
        code: str,
        dependencies: DependencyReport,
        hardware: HardwareInfo,
    ) -> ExecutionPlan:
        heavy = [r for r in dependencies.third_party if r in _HEAVY_PACKAGES]
        minutes = 2.0
        risks: List[str] = []
        needs_gpu = False
        if heavy:
            minutes = 25.0
            needs_gpu = any(p in {"torch", "tensorflow", "jax", "vllm"} for p in heavy)
            risks.append(f"Heavy ML packages detected: {', '.join(heavy)}")
        # Crude signal: long scripts or explicit training loops.
        loc = code.count("\n")
        if loc > 400:
            minutes += 5.0
        if any(tok in code for tok in ("for epoch", ".fit(", ".train(", "DataLoader")):
            minutes = max(minutes, 20.0)
            risks.append("Training/fitting loop detected")
        complexity = self.thresholds.classify(minutes)
        return ExecutionPlan(
            complexity=complexity,
            estimated_minutes=minutes,
            confidence=0.3,
            needs_gpu=needs_gpu,
            rationale="Static heuristic estimate (LLM planner unavailable).",
            risks=risks,
            source="heuristic",
        )


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
