"""Tests for the execution planner (LLM + heuristic)."""

from __future__ import annotations

from repgen.execution.dependencies import DependencyResolver
from repgen.execution.hardware import GPUInfo, HardwareInfo
from repgen.execution.planner import (
    Complexity,
    ComplexityThresholds,
    ExecutionPlanner,
)


def _hw(gpu=False):
    return HardwareInfo(
        cpu_count=8,
        total_ram_gb=16,
        available_ram_gb=8,
        free_disk_gb=100,
        gpus=[GPUInfo("Test GPU", 8000)] if gpu else [],
    )


def test_thresholds_classify():
    t = ComplexityThresholds(quick_max_minutes=10, medium_max_minutes=40)
    assert t.classify(5) is Complexity.QUICK
    assert t.classify(20) is Complexity.MEDIUM
    assert t.classify(60) is Complexity.LARGE


def test_heuristic_plan_trivial():
    planner = ExecutionPlanner(backend=None)
    deps = DependencyResolver().resolve("import os\nprint('hi')\n")
    plan = planner.plan("print('hi')", deps, _hw())
    assert plan.source == "heuristic"
    assert plan.complexity is Complexity.QUICK


def test_heuristic_plan_heavy_ml_is_large_and_flags_gpu():
    planner = ExecutionPlanner(backend=None)
    code = "import torch\nfor epoch in range(10):\n    model.train()\n"
    deps = DependencyResolver().resolve(code)
    plan = planner.plan(code, deps, _hw(gpu=False))
    assert plan.complexity in (Complexity.MEDIUM, Complexity.LARGE)
    assert plan.needs_gpu
    assert plan.gpu_shortfall  # no GPU present
    assert any("GPU" in r for r in plan.risks)


def test_llm_plan_used_when_available():
    class B:
        def generate(self, prompt, **kw):
            class R:
                text = (
                    '{"complexity":"medium","estimated_minutes":25,'
                    '"confidence":0.8,"needs_gpu":false,"peak_ram_gb":2,'
                    '"disk_gb":1,"rationale":"moderate","risks":["slow"]}'
                )
            return R()

    planner = ExecutionPlanner(backend=B())
    deps = DependencyResolver().resolve("print('x')")
    plan = planner.plan("print('x')", deps, _hw())
    assert plan.source == "llm"
    assert plan.complexity is Complexity.MEDIUM
    assert plan.estimated_minutes == 25
    assert "slow" in plan.risks


def test_llm_garbage_falls_back_to_heuristic():
    class B:
        def generate(self, prompt, **kw):
            class R:
                text = "not json at all"
            return R()

    planner = ExecutionPlanner(backend=B())
    deps = DependencyResolver().resolve("print('x')")
    plan = planner.plan("print('x')", deps, _hw())
    assert plan.source == "heuristic"


def test_render_contains_complexity():
    planner = ExecutionPlanner(backend=None)
    deps = DependencyResolver().resolve("print('x')")
    plan = planner.plan("print('x')", deps, _hw())
    assert "Complexity" in plan.render()
