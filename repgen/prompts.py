"""Prompt templates used across the RepGen agent."""

from __future__ import annotations

import json
from typing import Optional

# ==========================================================================
# Bug report refinement
# ==========================================================================


def refinement_prompt(bug_report_content: str) -> str:
    return f"""You are a software development assistant. Analyze and restructure this bug report.

Original bug report:
{bug_report_content}

Provide your analysis in exactly this format:

TITLE
[One-line summary of the core issue]

SYMPTOMS
- [Each observed problem]
- [Error messages exactly as shown, including the exception type]
- [All reported unexpected behaviors]

EXPECTED BEHAVIOR
[What should happen when the software works correctly]

REPRODUCTION STEPS
1. [First step to reproduce]
2. [Next step]

Begin your structured analysis:"""


# ==========================================================================
# Failure signature extraction (feeds the pseudo-symbolic verifier)
# ==========================================================================


def failure_signature_prompt(refined_report: str) -> str:
    return f"""Extract the expected failure signature from this bug report.

Bug report:
{refined_report}

Return ONLY a JSON object with this schema:
{{
  "exception_type": "<Python exception class name, or null if not an exception>",
  "message_substrings": ["<distinctive substrings expected in the error/output>"],
  "trigger_apis": ["<function/method names whose call triggers the bug>"]
}}

If a field is unknown, use null or an empty list. Output only the JSON object:"""


# ==========================================================================
# Exploration (ReAct)
# ==========================================================================


def exploration_system_prompt(tools_description: str) -> str:
    return f"""You are RepGen's exploration agent. Your job is to explore a code
repository and gather exactly the context needed to write a script that
REPRODUCES a reported bug (not to fix it).

You work in a loop. At each step, think briefly, then choose ONE tool.
Respond with a single line of JSON and nothing else, in this exact form:

{{"thought": "<short reasoning>", "tool": "<tool_name>", "args": {{<arguments>}}}}

You are given a structural map of the repository (modules, classes, and function
signatures) at the top of the transcript. Reason over it to decide where to look
before searching or reading.

Available tools:
{tools_description}

Guidelines:
- Use the repo map first to locate likely-relevant modules; use repo_map with a
  path prefix to zoom in, then search_code / read_file on the best candidates.
- Prefer reading the specific functions/classes named in the bug report.
- Note the exact import paths and function signatures a reproduction would need.
- Stop as soon as you have enough to write the reproduction, then call "finish"
  with the list of file paths that matter most and a short rationale.
- Do not exceed the step budget. Never invent file paths; discover them with tools."""


def exploration_finish_reminder() -> str:
    return (
        'You have reached the step budget. Respond now with the "finish" tool, '
        "listing the files that matter most for reproduction."
    )


# ==========================================================================
# Planning
# ==========================================================================


def plan_prompt(refined_report: str, context_text: str) -> str:
    return f"""You are a code generation planner. Create a detailed step-by-step plan
to reproduce this bug. Focus on concrete, technical steps with specific values
and assertions.

Bug Report:
{refined_report}

Relevant Code Context:
{context_text}

Requirements:
- Include specific technical details (dimensions, batch sizes, parameters)
- Focus only on reproducing the bug, not fixing it
- Include setup steps (imports, data preparation)
- Include a validation/observation step that surfaces the bug
- Make steps granular and specific

Output must be a valid JSON array of strings, for example:
[
    "Import the inception module from models/inception.py",
    "Create random input with shape (5, 299, 299, 3)",
    "Call inception_v3 with num_classes=1000",
    "Assert the loss is NaN to surface the bug"
]

Generate plan steps:"""


# ==========================================================================
# Code generation + repair
# ==========================================================================


def code_prompt(
    refined_report: str,
    context_text: str,
    plan: str,
    feedback: Optional[str] = None,
) -> str:
    prompt = f"""You are a senior engineer reproducing software bugs. Generate a
Python script that reproduces this bug.

Bug Report:
{refined_report}

Relevant Code Context:
{context_text}

Reproduction Plan:
{plan}"""

    if feedback:
        prompt += f"""

The previous attempt failed static verification. Fix these issues:
{feedback}"""

    prompt += """

Requirements:
1. A minimal, self-contained Python script.
2. Use only imports and APIs that appear in the provided context.
3. Include an explicit observation point (assert/print/try-except) that surfaces the bug.
4. Do not fix the bug; make it manifest.
5. Output ONLY the code inside a single ```python fenced block, nothing else."""
    return prompt


# ==========================================================================
# Structured LLM critique (replaces the old yes/no relevance check)
# ==========================================================================


def critique_prompt(refined_report: str, code: str) -> str:
    return f"""You are reviewing whether a generated script actually reproduces a
reported bug. Reason step by step, then judge.

Bug Report:
{refined_report}

Generated Script:
{code}

Return ONLY a JSON object:
{{
  "reproduces": true|false,
  "reasoning": "<brief step-by-step justification>",
  "issues": ["<concrete, actionable problems, if any>"]
}}

Output only the JSON object:"""


def build_context_text(context) -> str:
    """Render a RetrievedContext (or plain dict/list) into prompt text."""
    if hasattr(context, "as_prompt_text"):
        return context.as_prompt_text()
    return json.dumps(context, indent=2, default=str)
