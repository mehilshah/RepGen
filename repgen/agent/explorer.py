"""Exploration agent: a text-ReAct loop that gathers reproduction context."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, Optional

from ..backends import LLMBackend
from ..prompts import (
    exploration_finish_reminder,
    exploration_system_prompt,
)
from ..utils import extract_json_content
from .context import RetrievedContext
from .tools import TOOLS_DESCRIPTION, RepoToolbox

logger = logging.getLogger("repgen.agent.explorer")

ProgressCb = Optional[Callable[[str, Dict[str, Any]], None]]


def parse_action(text: str) -> Optional[Dict[str, Any]]:
    """Parse a ReAct action JSON object from a model response."""
    candidate = extract_json_content(text) or text
    for chunk in (candidate, text):
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict) and "tool" in obj:
                return obj
        except Exception:  # noqa: BLE001
            pass
    # Last resort: first {...} span containing a "tool" key.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict) and "tool" in obj:
                return obj
        except Exception:  # noqa: BLE001
            pass
    return None


class ExplorationAgent:
    def __init__(
        self,
        backend: LLMBackend,
        toolbox: RepoToolbox,
        max_steps: int = 12,
        progress_cb: ProgressCb = None,
    ):
        self.backend = backend
        self.toolbox = toolbox
        self.max_steps = max_steps
        self.progress_cb = progress_cb

    def _notify(self, event: str, **data: Any) -> None:
        if self.progress_cb:
            self.progress_cb(event, data)

    def explore(self, refined_report: str) -> RetrievedContext:
        system = exploration_system_prompt(TOOLS_DESCRIPTION)

        # Seed the agent with an organized structural map of the repository so it
        # reasons about *where* to look (dynamic, LLM-driven retrieval) instead of
        # relying on static similarity scores.
        overview = self.toolbox.map_overview()
        transcript: list[str] = [f"[repo map]\n{overview}"]
        self._notify("repo_map", overview=overview)

        for step in range(1, self.max_steps + 1):
            reminder = ""
            if step == self.max_steps:
                reminder = "\n" + exploration_finish_reminder()

            user = (
                f"Bug report:\n{refined_report}\n\n"
                f"Transcript so far:\n{chr(10).join(transcript) or '(empty)'}\n\n"
                f"Step {step}/{self.max_steps}. Respond with ONE action JSON.{reminder}"
            )
            response = self.backend.generate(user, system=system, max_tokens=1024)
            action = parse_action(response.text)

            if action is None:
                obs = (
                    "Could not parse an action. Reply with a single JSON object like "
                    '{"thought": "...", "tool": "list_dir", "args": {"path": "."}}'
                )
                transcript.append(f"[step {step}] (unparseable response)\n{obs}")
                self._notify("parse_error", step=step, raw=response.text)
                continue

            tool = str(action.get("tool", "")).strip()
            args = action.get("args") or {}
            thought = str(action.get("thought", "")).strip()
            self._notify("action", step=step, tool=tool, args=args, thought=thought)

            if tool == "finish":
                self.toolbox.context.rationale = str(
                    args.get("rationale", thought)
                ).strip()
                files = args.get("files") or []
                if isinstance(files, list):
                    self.toolbox.context.key_files = [str(f) for f in files]
                self._notify(
                    "finish", step=step, rationale=self.toolbox.context.rationale
                )
                break

            observation = self.toolbox.dispatch(tool, args)
            self._notify("observation", step=step, tool=tool, observation=observation)
            transcript.append(
                f"[step {step}] thought: {thought}\n"
                f"action: {tool} {json.dumps(args)}\n"
                f"observation:\n{observation}"
            )

        ctx = self.toolbox.context
        if not ctx.rationale:
            ctx.rationale = "Exploration ended without an explicit finish."
        # Ensure any files that were read are considered key files if none set.
        if not ctx.key_files:
            ctx.key_files = list(dict.fromkeys(s.path for s in ctx.snippets))
        return ctx
