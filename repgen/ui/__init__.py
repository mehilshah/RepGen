"""Rich terminal UI for RepGen's execution engine.

Provides a Claude-Code-style presentation layer over the execution pipeline's
progress events: streaming output, live progress, dependency-install status,
collapsible logs, clear error/verdict visualization, command visibility, and a
final summary — plus an interactive confirmation prompt for the Medium/Large
complexity gates.
"""

from __future__ import annotations

from .execution_view import ExecutionReporter, interactive_confirm

__all__ = ["ExecutionReporter", "interactive_confirm"]
