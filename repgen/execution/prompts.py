"""Prompt templates for the execution engine (planner / refine / reproduction).

Kept separate from :mod:`repgen.prompts` (which covers exploration and static
generation) so the runtime concerns live next to the code that uses them.
"""

from __future__ import annotations

from typing import Optional


def planner_prompt(
    code: str,
    dependencies: str,
    hardware: str,
    bug_report: Optional[str] = None,
) -> str:
    """Ask the LLM to estimate execution complexity given the host hardware."""
    report_block = f"\nBug report (context):\n{bug_report}\n" if bug_report else ""
    return f"""You are an execution-planning assistant. Estimate how expensive it
will be to run the following Python script on the described machine.

Script:
```python
{code}
```

Detected third-party dependencies: {dependencies or "none"}
{report_block}
Host hardware:
{hardware}

Consider: model training/inference, dataset downloads, large installs (e.g.
torch/tensorflow), heavy loops, network calls, and whether a GPU is required
but absent (which makes CPU fallback far slower).

Classify the run into exactly one bucket:
- "quick": completes within ~5-10 minutes.
- "medium": roughly 10-40 minutes.
- "large": more than ~40 minutes, or needs resources this machine lacks.

Return ONLY a JSON object with this schema:
{{
  "complexity": "quick" | "medium" | "large",
  "estimated_minutes": <number>,
  "confidence": <0.0-1.0>,
  "needs_gpu": true|false,
  "peak_ram_gb": <number>,
  "disk_gb": <number>,
  "rationale": "<one or two sentences>",
  "risks": ["<notable risk or resource concern>"]
}}

Output only the JSON object:"""


def refine_prompt(
    code: str,
    stdout: str,
    stderr: str,
    exception_type: Optional[str],
    traceback: str,
    goal: str,
) -> str:
    """Ask the LLM to repair a script that failed to execute correctly."""
    return f"""A Python script failed to execute as intended. Analyze the error
and produce a corrected version.

Goal:
{goal}

Current script:
```python
{code}
```

--- stdout ---
{stdout[-4000:] or "(empty)"}

--- stderr ---
{stderr[-4000:] or "(empty)"}

Detected exception: {exception_type or "none"}
{traceback[-2000:]}

Instructions:
1. Identify the most likely root cause (missing import, wrong API usage, bad
   path, environment issue, etc.).
2. Produce a corrected, self-contained script that still pursues the goal above.
3. Do NOT silence or hide the target bug if this is a reproduction script — only
   fix incidental errors that prevent the script from running.
4. Output ONLY the corrected code in a single ```python fenced block.

First, briefly state the root cause in one line, then the corrected code:"""


def reproduction_compare_prompt(
    bug_report: str,
    stdout: str,
    stderr: str,
    exception_type: Optional[str],
    traceback: str,
) -> str:
    """Ask the LLM whether the execution output reproduces the reported bug."""
    return f"""You are judging whether a script's ACTUAL execution output
reproduces a reported bug.

Reported bug:
{bug_report}

--- actual stdout ---
{stdout[-4000:] or "(empty)"}

--- actual stderr ---
{stderr[-4000:] or "(empty)"}

Observed exception: {exception_type or "none"}
{traceback[-2000:]}

Decide whether the actual output matches the reported failure (same error type,
same message/behavior, or the same wrong result). A crash unrelated to the
reported bug is NOT a reproduction.

Return ONLY a JSON object:
{{
  "reproduced": true|false,
  "confidence": <0.0-1.0>,
  "matching_evidence": ["<specific lines/phrases shared by report and output>"],
  "key_error": "<the decisive error/behavior, or empty>",
  "explanation": "<one or two sentences>",
  "debugging_insights": ["<if not reproduced, why, and what to try next>"]
}}

Output only the JSON object:"""
